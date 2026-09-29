"""
📡 Notification Stream (SSE) — badge ในแอปขยับทันทีโดยไม่ต้องรีเฟรช
=====================================================================
ปัญหาเดิม: `stores/notifications.ts` poll ทุก 30 วิ ⇒ คนที่เปิดแอปอยู่เห็น badge
ช้าได้ถึง 30 วิ (นี่คือความรู้สึก "ต้องรีเฟรช" ของผู้ใช้ — **คนละเรื่องกับ push**
ซึ่งแก้ "ปิดแอปอยู่ก็ยังเด้ง")

3 ชั้นที่ต้องพิสูจน์ แยกกันคนละเรื่อง:
  1) **trigger + `pg_notify`** (migration 020) — ยิงสัญญาณจริงตอน INSERT
  2) **`NotificationHub`** — fan-out ในโปรเซส + เพดาน + ทิ้งเมื่อคิวเต็ม
  3) **`GET /api/notifications/stream`** — frame แรกเป็น `snapshot` เสมอ + headers

⭐ **เทสต์ที่สำคัญที่สุดในไฟล์นี้: `test_D2_*`** — พิสูจน์ว่า **transaction ที่ rollback
   ไม่ยิงสัญญาณเลย** · เป็นเหตุผลหลักที่เลือก `pg_notify` แทนการ publish จาก Python
   ใน `notify*` (ซึ่งจะยิง **ก่อน** commit)

   **เหตุผลที่ publish ก่อน commit แย่ — แยกให้ถูก (สำคัญ):**
   เหตุผล *จริง* คือ **สัญญาณต้องไปถึงผู้ใช้ที่ต่ออยู่กับ replica อื่น** · backend รัน
   3 replica และผู้ใช้ 1 คนถูกถือโดย replica ใด replica หนึ่งเท่านั้น ⇒ การ publish
   ในโปรเซสจะถึงแค่ 1 ใน 3 ⇒ อีก 2 replica badge ค้างจน poll รอบถัดไป (30 วิ)
   — `pg_notify` ส่งผ่าน DB ⇒ ทุก replica ที่ LISTEN อยู่ได้รับครบ

   ⚠️ **ไม่ใช่** เพราะ "badge จะเพิ่มของที่ถูก rollback แล้วไม่ลดลง" — poke ที่หลุด
   จาก rollback ไม่ทำให้ยอดเพี้ยน เพราะ poke **ไม่มียอดติดมา** (client ไปถาม
   `get_unread_counts()` จาก DB เอง ⇒ ได้ยอดจริง) ⇒ ต้นทุนของ poke เกินคือ
   **request ที่เสียเปล่า 1 ครั้ง** ไม่ใช่ badge ผิด · อย่าเขียนเหตุผลนี้ผิดที่
   ไม่งั้นวันหน้าจะมีคนสรุปว่า `pg_notify` ไม่จำเป็น

   ⇒ ขอบเขตที่เทสต์นี้จับได้: **publish ระดับ DB ที่เกิดขึ้นก่อน commit** เท่านั้น
   (`await conn.execute("SELECT pg_notify(...)")` ใน `notify()`) — mutation ที่พิสูจน์แล้ว
   ว่าจับได้ · ส่วนการเรียก `hub._publish()` ในโปรเซส **เทสต์นี้ไม่จับ** (ไม่ผ่าน DB)
   และไม่ควรจับ — มันคือการละเมิด layering (service แตะ hub) ที่ควรจับตอน review

ตาม docs/rules/testing.md: ทุกเทสต์ยืนยัน DB ตรง ๆ ผ่าน db_pool ไม่เชื่อ response
"""
import asyncio
import contextlib
import importlib
import json
import random

import asyncpg
import pytest
import pytest_asyncio

from core.config import settings
from main import app
from services import auth_service, notification_service
from services.notification_stream import NotificationHub, StreamAtCapacity


# ============================================================
# Fixtures / helpers
# ============================================================

@pytest_asyncio.fixture
async def stream_world(db_pool):
    """student + student2 — พอสำหรับทดสอบ "สัญญาณไปถึงคนที่ถูกคนเดียว" """
    room_code = f"บ.{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        room_id = await conn.fetchval(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.5') RETURNING id",
            room_code, room_code,
        )

    users = {}
    for label, no in [("student", 1), ("student2", 2)]:
        sid = f"P{random.randint(1000, 9999)}{label[:2].upper()}"
        uid = await auth_service.register_user(
            db_pool, sid, "1234", f"{label} ทดสอบ", sid, room_code, no, "student"
        )
        users[label] = {
            "user_id": uid,
            "token": auth_service.create_access_token(uid),
            "room_id": room_id,
        }
    return users


def _auth(world, who="student"):
    return {"Authorization": f"Bearer {world[who]['token']}"}


async def _listen(dsn: str, channel: str | None = None):
    """เปิด connection แยกสำหรับ LISTEN — **นอก pool เหมือนของจริง** (ดู notification_stream.py)

    คืน `(conn, received)` โดย `received` เป็นลิสต์ที่ callback ต่อท้าย payload ดิบ
    """
    channel = channel or settings.NOTIFY_CHANNEL
    conn = await asyncpg.connect(dsn)
    received: list[str] = []
    # asyncpg เรียก callback ด้วย (connection, pid, channel, payload)
    await conn.add_listener(channel, lambda _c, _p, _ch, payload: received.append(payload))
    return conn, received


async def _wait_events(received: list[str], n: int, timeout: float = 5.0) -> list[str]:
    """รอจนได้ `n` event หรือหมดเวลา — LISTEN/NOTIFY เป็น async ที่ไม่มีการรับประกันเวลา

    ⚠️ ต้องวนรอ **ไม่ใช่ `sleep` ค่าคงที่** — เครื่อง CI ที่โหลดสูงจะทำให้ sleep สั้นเกิน
       แล้วเทสต์ล้มเป็นครั้งคราว (flake ที่หาเหตุยากที่สุด)
    """
    deadline = asyncio.get_running_loop().time() + timeout
    while len(received) < n and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.02)
    return received


async def _count_notifs(db_pool, user_id: int) -> int:
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM notifications WHERE user_id = $1", user_id
        )


async def _notify_one(conn, user_id: int, *, group_type: str = "issue_mine") -> None:
    """ยิง notification 1 แถวผ่านทางเข้าจริง (`notify`) — ไม่ INSERT เอง"""
    await notification_service.notify(
        conn,
        user_id=user_id,
        group_type=group_type,
        type="issue_update",
        title="หัวข้อทดสอบ",
        body="เนื้อหาทดสอบ",
        entity_type="issue",
        entity_id=1,
    )


# ============================================================
# 1) trigger + pg_notify (deep DB — ไม่ผ่าน HTTP เลย)
# ============================================================

@pytest.mark.asyncio
async def test_D1_insert_emits_notify_with_user_id(stream_world, db_pool, test_db_url):
    """INSERT notification → LISTEN ได้ payload ที่มี `user_id` ของ **ผู้รับ**"""
    uid = stream_world["student"]["user_id"]
    conn, received = await _listen(test_db_url)
    try:
        await _notify_one(db_pool, uid)
        await _wait_events(received, 1)

        assert len(received) == 1, f"ต้องได้ 1 สัญญาณ ขาด/เกิน = {received}"
        assert json.loads(received[0]) == {"user_id": uid}
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_D2_rolled_back_transaction_emits_nothing(
    stream_world, db_pool, test_db_url
):
    """★ เทสต์หัวใจ — transaction ที่ rollback ต้อง **ไม่ยิงสัญญาณเลย**

    คุณสมบัตินี้ได้ **ฟรี** จาก `pg_notify` (คิว NOTIFY ส่งตอน COMMIT เท่านั้น)
    ต่างจากการ publish จาก Python ใน `notify*` ซึ่งจะยิง **ก่อน** commit
    ⇒ เหตุผลเต็ม ๆ ว่าทำไม publish ก่อน commit ถึงแย่ (และทำไม *ไม่ใช่* เรื่อง badge เพี้ยน)
    อยู่ใน docstring หัวไฟล์ — **อ่านก่อนแก้เหตุผลในคอมเมนต์ใด ๆ ที่นี่**

    **mutation ที่ทำให้เทสต์นี้แตก (พิสูจน์แล้ว):** ย้าย publish ไปไว้ใน `notify()`
    เป็นคำสั่งระดับ DB — `await conn.execute("SELECT pg_notify($1,$2)", ...)`
    บน connection แยก **ที่ชี้ฐานข้อมูลเดียวกับที่เทสต์ LISTEN อยู่** ⇒ จะได้ 2 event

    ⚠️ **กับดักตอนทำ mutation (เจอจริง):** ถ้าเปิด connection แยกด้วย
    `settings.DATABASE_URL` จะได้คนละฐานข้อมูลกับที่เทสต์ใช้ — เพราะ `test_db_url`
    ใน `conftest.py` **คืนค่า `DATABASE_URL` เดิมก่อน `yield`** (สลับเป็น `test_db_<hex>`
    แค่ตอนรัน `init_db`) · NOTIFY แยกตามฐานข้อมูล ⇒ สัญญาณไปไม่ถึง ⇒ **เทสต์ผ่านทั้งที่ควรแตก**
    = mutation ที่หลอกตัวเอง ⇒ ต้องอ่าน DSN จาก `conn.get_settings()` ของ connection
    ที่ caller ส่งมา ไม่ใช่จาก `settings`
    """
    uid = stream_world["student"]["user_id"]
    conn, received = await _listen(test_db_url)
    try:
        # (ก) transaction ที่ commit ปกติ → ต้องได้ 1
        async with db_pool.acquire() as c:
            async with c.transaction():
                await _notify_one(c, uid)
        await _wait_events(received, 1)
        assert len(received) == 1

        # (ข) transaction ที่ rollback → ต้องไม่ได้เพิ่ม
        with pytest.raises(RuntimeError):
            async with db_pool.acquire() as c:
                async with c.transaction():
                    await _notify_one(c, uid)
                    raise RuntimeError("จำลองความล้มเหลวกลาง transaction")

        # ให้เวลาสัญญาณ(ถ้ามี)วิ่งมาถึงก่อนตัดสิน — ไม่งั้นเทสต์ผ่านเพราะ "ยังไม่ถึง"
        await asyncio.sleep(0.4)
        assert len(received) == 1, (
            f"rollback แล้วยังมีสัญญาณหลุดออกมา {len(received) - 1} อัน "
            "⇒ มีคนไป publish ก่อน commit (ดู docstring ของ migration 020)"
        )

        # แถวใน DB ก็ต้องไม่มี — ยืนยันว่า rollback ทำงานจริง ไม่ใช่เทสต์ที่พิสูจน์อากาศ
        assert await _count_notifs(db_pool, uid) == 1
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_D3_payload_carries_no_message_content(stream_world, db_pool, test_db_url):
    """🔒 payload ต้องมี **แค่ `user_id`** — ห้ามมี title/body หลุดไปกับสัญญาณ

    payload วิ่งผ่าน **ทุกโปรเซสที่ LISTEN** ⇒ ถ้าใส่เนื้อความไว้ การกรองพลาดครั้งเดียว
    = ข้อความรั่วข้ามผู้ใช้ · และ `notify_fanout` ยิงถึงพันคน = payload ต้องเล็กสุด
    """
    uid = stream_world["student"]["user_id"]
    conn, received = await _listen(test_db_url)
    try:
        await notification_service.notify(
            db_pool,
            user_id=uid,
            group_type="issue_mine",
            type="issue_update",
            title="ความลับเฉพาะคนนี้",
            body="เนื้อความที่ห้ามหลุด",
            entity_type="issue",
            entity_id=42,
        )
        await _wait_events(received, 1)

        raw = received[0]
        assert set(json.loads(raw).keys()) == {"user_id"}
        assert "ความลับเฉพาะคนนี้" not in raw
        assert "เนื้อความที่ห้ามหลุด" not in raw
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_D4_bulk_executemany_emits_per_row(stream_world, db_pool, test_db_url):
    """`notify_bulk` ใช้ `executemany` (asyncpg ห่อเป็น pipeline) — ต้องยิง **ต่อแถว**

    ถ้า trigger ไม่ทำงานในเส้นทางนี้ ผู้ใช้จะไม่เห็น badge ขยับทั้งที่ในลิสต์มีของ
    (ระบบดูปกติทุกอย่าง ⇒ หาสาเหตุยาก)
    """
    uids = [stream_world["student"]["user_id"], stream_world["student2"]["user_id"]]
    conn, received = await _listen(test_db_url)
    try:
        await notification_service.notify_bulk(
            db_pool, uids,
            group_type="board", type="board_new", title="บอร์ดใหม่",
            body="มีบอร์ดใหม่", entity_type="board", entity_id=7,
        )
        await _wait_events(received, 2)

        assert len(received) == 2
        assert {json.loads(p)["user_id"] for p in received} == set(uids)
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_D5_fanout_emits_one_signal_per_recipient(
    stream_world, db_pool, test_db_url
):
    """`notify_fanout` = `INSERT … SELECT` หลายแถวจากคำสั่งเดียว → ต้องได้สัญญาณครบ"""
    conn, received = await _listen(test_db_url)
    try:
        await notification_service.notify_fanout(
            db_pool,
            group_type="board", type="board_new", title="ประกาศ",
            body="ประกาศถึงทุกคน", entity_type="board", entity_id=9,
        )
        # ทั้ง student และ student2 active ⇒ 2 แถว
        await _wait_events(received, 2)
        assert len(received) == 2
        assert {json.loads(p)["user_id"] for p in received} == {
            stream_world["student"]["user_id"],
            stream_world["student2"]["user_id"],
        }
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_D6_mark_read_emits_nothing(stream_world, db_pool, test_db_url):
    """`mark_read` เป็น **UPDATE** — ต้องไม่ยิงสัญญาณ (trigger เป็น INSERT-only โดยเจตนา)

    เหตุผลที่ยังไม่ทำ multi-tab sync ของ "อ่านแล้ว": `mark_read(all_=True)` แตะได้
    หลายร้อยแถวในคำสั่งเดียว ⇒ จะได้ NOTIFY หลายร้อยข้อความต่อการกดหนึ่งครั้ง
    (ทางที่ถูกถ้าจะทำวันหลัง = statement-level trigger — บันทึกใน migration 020)

    ⇒ เทสต์นี้กันคนที่เผลอเปลี่ยน trigger เป็น `AFTER INSERT OR UPDATE` โดยไม่รู้ตัว
    """
    uid = stream_world["student"]["user_id"]
    conn, received = await _listen(test_db_url)
    try:
        await _notify_one(db_pool, uid)
        await _wait_events(received, 1)
        assert len(received) == 1

        updated = await notification_service.mark_read(db_pool, uid, all_=True)
        assert updated == 1, "ต้อง mark ได้จริง ไม่งั้นเทสต์นี้พิสูจน์อากาศ"

        await asyncio.sleep(0.4)
        assert len(received) == 1, "mark_read (UPDATE) ไม่ควรยิงสัญญาณ"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_D7_pref_gate_still_silences_stream(stream_world, db_pool, test_db_url):
    """ปิดกลุ่มไว้ (A2) → ทั้ง notification และสัญญาณต้อง **เงียบพร้อมกัน**

    ถ้าเงียบแค่ notification แต่สัญญาณยังออก ⇒ client จะยิงถามยอดใหม่ฟรี ๆ ทุกครั้ง
    (ไม่ผิด แต่เสียเปล่า) · ที่แย่กว่าคือถ้าวันหนึ่งมีคนแยก gate ออกจากกันแล้วเหลือ
    ทางใดทางหนึ่ง = สัญญาณกับข้อมูลไม่ตรงกัน
    """
    uid = stream_world["student"]["user_id"]
    async with db_pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO notification_preferences (user_id, group_type, enabled)
            VALUES ($1, 'issue_mine', FALSE)
            """,
            uid,
        )

    conn, received = await _listen(test_db_url)
    try:
        await _notify_one(db_pool, uid)
        await asyncio.sleep(0.4)

        assert received == []
        assert await _count_notifs(db_pool, uid) == 0
    finally:
        await conn.close()


# ============================================================
# 2) NotificationHub — fan-out ในโปรเซส (ไม่แตะ DB เลย)
# ============================================================

@pytest.mark.asyncio
async def test_H1_subscribe_and_unsubscribe_bookkeeping():
    """นับผู้ใช้ ≠ นับแท็บ · ถอนแล้วต้องไม่มี key ค้าง"""
    hub = NotificationHub(max_subscribers=10)
    q1 = hub.subscribe(1)
    q2 = hub.subscribe(1)  # แท็บที่สองของคนเดิม
    hub.subscribe(2)

    assert hub.subscriber_count == 2, "คนเดียวเปิด 2 แท็บ = 1 ผู้ใช้"
    assert hub.connection_count == 3

    hub.unsubscribe(1, q1)
    assert hub.connection_count == 2, "ถอนแท็บเดียวต้องไม่กระทบแท็บอื่น"

    hub.unsubscribe(1, q2)
    assert 1 not in hub._subscribers, "คนสุดท้ายออกแล้วต้องไม่เหลือ key ที่มีเซตว่าง"
    assert hub.subscriber_count == 1

    # ถอนซ้ำ/ถอนคนที่ไม่มี = ต้องไม่ raise (generator อาจถูกยกเลิกซ้อน)
    hub.unsubscribe(1, q2)
    hub.unsubscribe(999, q1)


@pytest.mark.asyncio
async def test_H2_publish_reaches_only_target_user():
    """🔒 สัญญาณของผู้ใช้คนหนึ่งต้องไม่ปลุก queue ของคนอื่น"""
    hub = NotificationHub(max_subscribers=10)
    mine = hub.subscribe(1)
    other = hub.subscribe(2)

    hub._publish(1)

    assert mine.qsize() == 1
    assert other.qsize() == 0, "สัญญาณรั่วข้ามผู้ใช้"


@pytest.mark.asyncio
async def test_H3_publish_reaches_every_tab_of_that_user():
    """ผู้ใช้คนเดียวเปิด 3 แท็บ = ทั้ง 3 ต้องตื่นพร้อมกัน"""
    hub = NotificationHub(max_subscribers=10)
    queues = [hub.subscribe(1) for _ in range(3)]

    hub._publish(1)

    assert [q.qsize() for q in queues] == [1, 1, 1]


@pytest.mark.asyncio
async def test_H4_full_queue_drops_signal_without_raising():
    """คิวเต็ม → ทิ้งสัญญาณ **ไม่ raise** และนับ `stale_dropped`

    ⭐ ถูกต้องเพราะ event เป็น "ธง dirty" ไม่ใช่ข้อมูล (ดู docstring notification_stream.py):
       มีสัญญาณค้างอยู่แล้ว 1 อัน = เพียงพอ · client ไปถามยอดจริงจาก DB อยู่ดี
    """
    hub = NotificationHub(max_subscribers=10)
    q = hub.subscribe(1)

    hub._publish(1)   # เต็มคิว (maxsize=1)
    hub._publish(1)   # ถูกทิ้ง
    hub._publish(1)   # ถูกทิ้ง

    assert q.qsize() == 1
    assert hub.stale_dropped == 2

    # บริโภคแล้วต้องรับได้อีก (ไม่ใช่ค้างถาวร)
    q.get_nowait()
    hub._publish(1)
    assert q.qsize() == 1


@pytest.mark.asyncio
async def test_H5_capacity_blocks_new_users_but_not_existing_tabs():
    """เพดานนับที่จำนวน *ผู้ใช้* — คนที่มีแท็บอยู่แล้วเปิดเพิ่มได้เสมอ"""
    hub = NotificationHub(max_subscribers=2)
    q1 = hub.subscribe(1)
    q2 = hub.subscribe(2)

    assert hub.at_capacity(3) is True
    assert hub.at_capacity(1) is False, "มีแท็บอยู่แล้ว = ไม่กินที่เพิ่ม"

    with pytest.raises(StreamAtCapacity):
        hub.subscribe(3)

    # คนที่มีอยู่แล้วยังเปิดแท็บเพิ่มได้ แม้เต็ม (เพดานนับ "ผู้ใช้" ไม่ใช่ "แท็บ")
    hub.subscribe(1)
    assert hub.connection_count == 3

    # ถอนคนที่ 2 ออกหมด → ที่ว่างกลับมาใช้ได้
    hub.unsubscribe(2, q2)
    assert hub.at_capacity(3) is False
    hub.subscribe(3)
    assert hub.subscriber_count == 2

    # ถอนซ้ำ = no-op ไม่ raise (generator อาจถูกยกเลิกซ้อน)
    hub.unsubscribe(2, q2)
    assert hub.connection_count == 3
    hub.unsubscribe(1, q1)


@pytest.mark.asyncio
async def test_H6_publish_to_unknown_user_is_noop():
    """ยิงหาคนที่ไม่มีผู้ฟัง = เงียบ ไม่ raise (เกิดจริงทุกครั้งที่ผู้ใช้ปิดแอป)"""
    hub = NotificationHub(max_subscribers=10)
    hub._publish(12345)
    assert hub.stale_dropped == 0


@pytest.mark.asyncio
async def test_H7_size_zero_queue_still_never_raises():
    """ผู้ใช้หลายแท็บถูกถอนไปหมดกลางทาง — `_publish` ต้องไม่พัง"""
    hub = NotificationHub(max_subscribers=10)
    q = hub.subscribe(1)
    hub.unsubscribe(1, q)
    hub._publish(1)
    assert hub.stale_dropped == 0


@pytest.mark.asyncio
async def test_H8_stop_clears_subscribers_and_is_idempotent():
    """`stop()` ต้องล้างผู้ฟังทั้งหมด — ไม่งั้น memory โตข้ามรอบ reload"""
    hub = NotificationHub(max_subscribers=10)
    hub.subscribe(1)
    hub.subscribe(2)
    assert hub.subscriber_count == 2

    await hub.stop()
    assert hub.subscriber_count == 0
    assert hub.is_connected is False

    await hub.stop()  # เรียกซ้ำต้องไม่ raise


@pytest.mark.asyncio
async def test_H9_start_never_raises_on_bad_dsn(monkeypatch):
    """🚨 `start()` ต้อง **ไม่ raise** แม้ต่อ DB ไม่ได้

    เหตุผล: ถ้า LISTEN ต่อไม่ขึ้น ระบบยังต้องทำงาน (in-app เหลือ poll 30 วิ)
    ⇒ การทำให้ lifespan ล้มเพราะ "ของที่ทำให้เร็วขึ้น" = ปิดระบบทั้งระบบเพื่อของประดับ
    """
    hub = NotificationHub(max_subscribers=10)
    try:
        await hub.start("postgresql://nobody:nopass@127.0.0.1:1/nothing")
        # ให้ supervisor ได้ลองจริงหนึ่งรอบ (แล้วล้มเหลว) — ต้องไม่ทำให้เทสต์พัง
        await asyncio.sleep(0.5)
        assert hub.is_connected is False
    finally:
        await hub.stop()


# ============================================================
# 3) GET /api/notifications/stream
# ============================================================
#
# 🚨 **ทำไมไม่ใช้ `TestClient` กับ endpoint นี้ — อ่านก่อนแก้**
#
# `TestClient` ของ Starlette บัฟเฟอร์ body ทั้งก้อนไว้ใน `io.BytesIO` แล้วปล่อยออกมา
# หลังแอป **return** เท่านั้น (`starlette/testclient.py` L343-345):
#
#     with self.portal_factory() as portal:
#         response_complete = portal.call(anyio.Event)
#         portal.call(self.app, scope, receive, send)   # ← บล็อกจนแอป "คืนค่า"
#
# แต่ generator ของ SSE ไม่มีวันคืนค่า (`while True` + `queue.get()`) ⇒ `client.stream()`
# **ค้างตลอดกาล** ตั้งแต่ `__enter__` — ไม่ใช่ "ช้า" แต่เป็น **deadlock**
# (อาการที่วัดได้จริง: pytest ทุก thread อยู่ใน `futex_wait` และ CPU ไม่ขยับเลย 8 วิ)
#
# ⚠️ `httpx.ASGITransport` **ก็ไม่ช่วย** — มันบัฟเฟอร์เหมือนกัน (`body_parts.append`
#    แล้ว `await self.app(...)`) ดู `httpx/_transports/asgi.py`
# ⇒ **client มาตรฐานทั้งสองตัวทดสอบสตรีมไม่มีวันจบไม่ได้** ไม่ใช่ข้อจำกัดของโค้ดเรา
#
# ⇒ ทางเดียวที่ตรงความจริงคือ **ขับ ASGI app เอง**: ประกอบ scope, ให้ `send` ของเราเอง,
#   รันเป็น task แล้วอ่าน message ทีละก้อนจาก queue · ได้ 2 อย่างที่ TestClient ให้ไม่ได้:
#     1. อ่าน frame ทีละอันได้จริง (streaming จริง ไม่ใช่รอจบแล้วค่อยอ่าน)
#     2. **สั่ง disconnect ได้เอง** ⇒ ตรวจ `finally`/unsubscribe ได้ตรง ๆ (E6)

# sentinel — ใส่ท้ายคิวเมื่อ app task จบ เพื่อบอกตัวอ่านว่า "ไม่มีอะไรอีกแล้ว"
_STREAM_DONE = object()


@pytest_asyncio.fixture
async def stream_app(db_pool):
    """ติด `db_pool` ของเทสต์เข้า `app.state` — สิ่งเดียวที่ lifespan ทำที่เราต้องใช้

    `get_db_pool()` อ่าน `request.app.state.db_pool` ตรง ๆ ⇒ การยัด pool ของเทสต์เข้าไป
    เทียบเท่ากับที่ lifespan ทำ แต่ **ไม่ต้องรัน `init_db` + `seed_default_users` + `hub.start`
    ซ้ำอีก 7 รอบ** · และได้เปรียบจริง: เป็น **pool ตัวเดียวกับที่เทสต์ใช้ assert**
    ⇒ deep-DB verify เป็นการยืนยันของจริง ไม่ใช่คนละ connection ที่อาจไม่เห็นกัน

    (hub ไม่ต้อง start — เทสต์ชุดนี้ตรวจ snapshot/heartbeat/เพดาน/disconnect ซึ่งไม่พึ่ง
     connection ของ LISTEN · ส่วนเส้นทาง LISTEN มีเทสต์ D1-D7 คุมอยู่แล้ว)
    """
    missing = object()
    previous = getattr(app.state, "db_pool", missing)
    app.state.db_pool = db_pool
    try:
        yield app
    finally:
        if previous is missing:
            del app.state.db_pool
        else:
            app.state.db_pool = previous


class _SseSession:
    """สตรีม SSE หนึ่งครั้ง — ขับ ASGI app ตรง ๆ (เหตุผลยาวอยู่ข้างบน)"""

    def __init__(self, asgi_app, *, headers: dict[str, str], path: str) -> None:
        self._app = asgi_app
        self._scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
        # ⭐ ตั้งเมื่อ "client หาย" — ปลุก `listen_for_disconnect` ของ Starlette ให้คืน
        #    `http.disconnect` ⇒ task group ถูกยกเลิก ⇒ generator ถูกเก็บกวาด
        #    = **เส้นทางเดียวกับที่เกิดจริงบน production** ไม่ใช่การ cancel เอง
        self._gone = asyncio.Event()
        self._send_q: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None

        self.status: int | None = None
        self.headers: dict[str, str] = {}
        self.body_text = ""
        # ⚠️ `status` มาก่อน body เสมอ (`http.response.start` แล้วค่อย `…body`) ⇒ รู้ status
        #    ยังไม่ได้แปลว่ามี body ให้อ่าน — ต้องมีธงแยก (E7 เจอจริง: body ยังว่าง)
        self.body_complete = False
        self.frames: list[list[str]] = []
        self.error: BaseException | None = None
        self.closed_gracefully: bool | None = None
        self._buf = ""

    # ---------------- ขับแอป ----------------

    async def _receive(self) -> dict:
        """`receive` ของ ASGI — บล็อกไว้จนกว่าเทสต์จะบอกว่า client หาย

        ⚠️ **ไม่คืน `http.request` แม้แต่ครั้งแรก** โดยเจตนา — endpoint นี้เป็น GET ที่อ่าน
           แต่ header ไม่มีใครอ่าน body ⇒ message ปลอมมีแต่จะทำให้ `is_disconnected()`
           (ที่ Starlette เรียกทุกครั้งหลัง heartbeat timeout) เข้าใจผิดว่ายังเชื่อมต่ออยู่
           · การบล็อกไว้ตอบถูกทั้งสองทาง: `listen_for_disconnect` รอต่อไป ไม่ตัดสายก่อนเวลา
        """
        await self._gone.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: dict) -> None:
        self._send_q.put_nowait(message)

    def _on_task_done(self, task: asyncio.Task) -> None:
        self.error = None if task.cancelled() else task.exception()
        self._send_q.put_nowait(_STREAM_DONE)

    async def start(self) -> "_SseSession":
        self._task = asyncio.create_task(self._app(self._scope, self._receive, self._send))
        self._task.add_done_callback(self._on_task_done)
        # รอ `http.response.start` — ยังไม่ได้ = แอปยังไม่ตอบอะไรเลย (ไม่ใช่ "สตรีมเปล่า")
        await self._drain(lambda: self.status is not None, timeout=5.0)
        return self

    # ---------------- อ่านผล ----------------

    def _handle(self, message: dict) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
            self.headers = {
                k.decode().lower(): v.decode() for k, v in message.get("headers", [])
            }
            return
        if message["type"] != "http.response.body":
            return
        chunk = message.get("body", b"")
        if chunk:
            text = chunk.decode("utf-8")
            self.body_text += text
            self._feed(text)
        if not message.get("more_body", False):
            self.body_complete = True

    def _feed(self, text: str) -> None:
        """ประกอบ frame จาก chunk ดิบ — **ตรรกะเดียวกับ `createSseParser` ฝั่ง client**

        ⭐ ไม่ใช้ `iter_lines()` ของ httpx โดยเจตนา — อยากให้สะท้อนภาระจริงของ client
           (ต้องแบก "เศษ frame ข้าม chunk" ไว้เอง) และไม่ผูกกับ semantics ของ `iter_lines()`
           ที่อาจไม่ข้ามบรรทัดว่าง ซึ่งเป็นตัวแบ่ง frame พอดี
        """
        self._buf += text.replace("\r\n", "\n")
        parts = self._buf.split("\n\n")
        self._buf = parts.pop()  # เศษที่ยังไม่จบ frame
        for part in parts:
            lines = [ln for ln in part.split("\n") if ln]
            if lines:
                self.frames.append(lines)

    async def _drain(self, predicate, timeout: float) -> bool:
        """ประมวลผล message จากแอปจนกว่า `predicate()` เป็นจริง (หรือหมดเวลา/แอปจบ)"""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not predicate():
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                message = await asyncio.wait_for(self._send_q.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            if message is _STREAM_DONE:
                break
            self._handle(message)
        return predicate()

    async def read_frames(self, want: int, timeout: float = 5.0) -> list[list[str]]:
        """อ่านจนได้ `want` frame (หรือหมดเวลา) แล้วคืนทั้งหมดที่ได้"""
        await self._drain(lambda: len(self.frames) >= want, timeout)
        return self.frames

    async def read_body(self, timeout: float = 5.0) -> str:
        """อ่าน body จนจบ — ใช้กับ response ที่เป็นก้อนเดียว (401/503) ไม่ใช่สตรีม

        ⚠️ ต้องเรียกแยกจาก `start()` เพราะ `start()` รอแค่ `http.response.start`
           ⇒ ตอนนั้น body อาจยังมาไม่ถึง (เจอจริงกับ E7: `body_text` ว่างเปล่า)
        """
        await self._drain(lambda: self.body_complete, timeout)
        return self.body_text

    # ---------------- ปิด ----------------

    async def aclose(self, timeout: float = 5.0) -> bool:
        """จำลอง client ตัดสาย แล้ว **รอให้แอปเก็บกวาดเอง**

        คืน `True` = แอปจบเองภายในเวลา ⇒ generator ถูกยกเลิกและ `finally` ทำงานครบ
        คืน `False` = ต้องบังคับ `cancel()` ⇒ **มีอะไรค้าง** (E6 ใช้ตัวนี้จับ)
        """
        self._gone.set()
        if self._task is None:
            return True
        graceful = True
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout=timeout)
        except asyncio.TimeoutError:
            graceful = False
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass  # เก็บไว้ที่ self.error แล้ว (done callback)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — ดู self.error
            pass
        self._task = None
        return graceful


@contextlib.asynccontextmanager
async def open_stream(asgi_app, world=None, *, headers=None, who: str = "student"):
    """เปิดสตรีมแล้วปิดให้เสมอ — `session.closed_gracefully` มีค่าหลังออกจากบล็อก"""
    session = _SseSession(
        asgi_app,
        headers=_auth(world, who) if headers is None else headers,
        path="/api/notifications/stream",
    )
    await session.start()
    try:
        yield session
    finally:
        session.closed_gracefully = await session.aclose()


@pytest.mark.asyncio
async def test_E1_stream_requires_login(stream_app, stream_world):
    """ไม่มี token → 401 (ไม่ใช่ 500 และไม่ใช่สตรีมเปล่าที่ค้าง)"""
    async with open_stream(stream_app, headers={}) as s:
        assert s.status == 401


@pytest.mark.asyncio
async def test_E2_stream_rejects_api_key(stream_app, stream_world):
    """`X-API-Key` (system RPC) → 401 เพราะ `get_current_user` คืน `user_id=None`

    ⚠️ ต้องเป็น 401 ไม่ใช่ 500 — บทเรียนเดียวกับ `/preferences` และ `/push/status`
    """
    async with open_stream(
        stream_app, headers={"X-API-Key": settings.API_KEY}
    ) as s:
        assert s.status == 401


@pytest.mark.asyncio
async def test_E3_first_frame_is_snapshot_with_live_counts(stream_app, stream_world):
    """★ frame แรกต้องเป็น `snapshot` ที่มียอดจริง — หัวใจของการต่อใหม่แล้วกลับมาตรง

    ถ้าไม่มี snapshot: client ที่เน็ตกระตุกจะค้างกับยอดเก่าจนกว่า poll รอบถัดไป
    = กลับไปช้า 30 วิ (จุดที่งานนี้ตั้งใจจะแก้)
    """
    async with open_stream(stream_app, stream_world) as s:
        assert s.status == 200
        assert s.headers["content-type"].startswith("text/event-stream")
        assert s.headers["cache-control"] == "no-cache, no-transform"
        assert s.headers["x-accel-buffering"] == "no"

        frames = await s.read_frames(want=1)

    assert len(frames) >= 1, "ไม่ได้ frame แรกภายในเวลา"
    first = frames[0]
    assert first[0] == "event: snapshot"

    data_line = next(l for l in first if l.startswith("data:"))
    payload = json.loads(data_line[len("data:"):].strip())
    assert payload == {"counts": {g: 0 for g in notification_service.GROUP_TYPES}, "total": 0}


@pytest.mark.asyncio
async def test_E4_snapshot_reflects_unread_rows(stream_app, stream_world, db_pool):
    """ยอดใน snapshot ต้องตรงกับ DB จริง (deep-DB verify) — ไม่ใช่ 0 ตายตัว"""
    uid = stream_world["student"]["user_id"]
    await _notify_one(db_pool, uid, group_type="board")

    expected = await notification_service.get_unread_counts(db_pool, uid)
    assert expected["total"] == 1, "ต้องมีของให้ตรวจก่อน ไม่งั้นเทสต์พิสูจน์อากาศ"

    async with open_stream(stream_app, stream_world) as s:
        assert s.status == 200
        frames = await s.read_frames(want=1)

    data_line = next(l for l in frames[0] if l.startswith("data:"))
    assert json.loads(data_line[len("data:"):].strip()) == expected


@pytest.mark.asyncio
async def test_E5_heartbeat_is_a_comment_frame(stream_app, stream_world, monkeypatch):
    """⏱️ เมื่อไม่มีความเคลื่อนไหว ต้องมี heartbeat `: ping` — กัน proxy ตัดสาย

    comment frame (`:` ขึ้นต้น) ไม่ trigger event ฝั่ง client ⇒ ใช้เป็นสัญญาณล้วน ๆ
    """
    monkeypatch.setattr(settings, "STREAM_HEARTBEAT_SECONDS", 0.1)

    async with open_stream(stream_app, stream_world) as s:
        assert s.status == 200
        frames = await s.read_frames(want=2)

    assert frames[0][0] == "event: snapshot"
    assert frames[1] == [": ping"], f"frame ที่สองต้องเป็น heartbeat แต่ได้ {frames[1]}"


@pytest.mark.asyncio
async def test_E6_unsubscribes_when_client_disconnects(stream_app, stream_world):
    """🚨 ปิดสตรีมแล้วต้องถอนผู้ฟังออกจาก hub — ไม่งั้น leak ที่ไม่มีอาการ

    ถ้าลืม: แท็บที่ปิดไปแล้วค้างใน dict ตลอดอายุโปรเซส ⇒ memory โตไม่หยุด และ
    `_publish` เอา event ไปใส่คิวที่ไม่มีใครอ่าน (ช้าแต่ไม่พัง = อันตรายเพราะเงียบ)

    ⭐ ตรวจ **สองชั้น**: (1) hub ว่างจริง (2) แอปจบเองโดยไม่ต้องบังคับ cancel
       ⇒ ชั้นที่สองจับ "generator ไม่ถูกยกเลิก" ซึ่งเป็นรากของ leak ทุกชนิด
    """
    from services import notification_stream as ns

    before = ns.hub.subscriber_count
    async with open_stream(stream_app, stream_world) as s:
        assert s.status == 200
        await s.read_frames(want=1)
        # ลงทะเบียนแล้วจริง — ไม่งั้นเทสต์นี้ผ่านเพราะ "ไม่มีอะไรให้ถอน" (พิสูจน์อากาศ)
        assert ns.hub.subscriber_count == before + 1

    assert s.closed_gracefully is True, (
        "แอปไม่จบเองหลัง client ตัดสาย — ต้องบังคับ cancel ⇒ generator ไม่ถูกเก็บกวาด"
    )
    assert ns.hub.subscriber_count == before, (
        f"ผู้ฟังค้างใน hub {ns.hub.subscriber_count - before} ราย — `finally` ถอนไม่ทำงาน"
    )


@pytest.mark.asyncio
async def test_E7_returns_503_when_at_capacity(stream_app, stream_world, monkeypatch):
    """เพดานเต็ม → **503 พร้อมข้อความบอกว่ายังได้ทุก 30 วิ** ไม่ใช่สตรีมเปล่าที่เงียบ

    ⚠️ ต้องเช็ค **ก่อน** เข้า generator — พอเข้าไปแล้ว HTTP status ถูกส่งไปแล้ว
       ⇒ ตอบ 503 ไม่ได้ (นี่คือเหตุที่ `at_capacity()` แยกจาก `subscribe()`)
    """
    from services import notification_stream as ns

    monkeypatch.setattr(ns.hub, "_max_subscribers", 0)

    async with open_stream(stream_app, stream_world) as s:
        assert s.status == 503
        body = await s.read_body()

    assert "30 วินาที" in json.loads(body)["detail"]

# ============================================================
# 4) migration 020 — ต้องอยู่ท้ายไฟล์ (มัน DROP ของจริง)
# ============================================================

@pytest.mark.asyncio
async def test_M1_migration_020_is_idempotent_and_restores_trigger(
    stream_world, db_pool, test_db_url
):
    """ลบ trigger + function ทิ้ง → `upgrade()` 2 ครั้ง → ต้องกลับมาครบและทำงานได้

    (รันท้ายไฟล์โดยเจตนา เพราะมัน DROP ของจริง — `upgrade()` ต้องสร้างคืนครบ
    ไม่งั้นเทสต์ไฟล์อื่นที่รันต่อจะพังด้วยเหตุผลผิด)

    **mutation:** ลบ `DROP TRIGGER IF EXISTS` ใน migration ⇒ รอบที่สอง error
    "trigger already exists"
    """
    stream_world
    mig = importlib.import_module("migrations.020_notifications_pg_notify")

    async with db_pool.acquire() as conn:
        await conn.execute("DROP TRIGGER IF EXISTS trg_notifications_stream ON notifications")
        await conn.execute("DROP FUNCTION IF EXISTS notifications_stream_notify()")

        assert await conn.fetchval(
            "SELECT COUNT(*) FROM pg_trigger WHERE tgname = 'trg_notifications_stream'"
        ) == 0, "ต้องลบได้จริงก่อนทดสอบ"

        await mig.upgrade(conn)
        await mig.upgrade(conn)  # idempotent — รันซ้ำต้องไม่ error

        # trigger เกิดจริงและเปิดใช้งาน ('O' = origin, ไม่ใช่ 'D' = disabled)
        # ⚠️ `tgenabled` เป็นชนิด "char" ⇒ asyncpg คืน bytes ถ้าไม่ cast
        assert await conn.fetchval(
            """
            SELECT tgenabled::text FROM pg_trigger
            WHERE tgname = 'trg_notifications_stream' AND NOT tgisinternal
            """
        ) == "O"

        # ผูกกับ function ที่ถูกตัว และยิง AFTER INSERT (ไม่ใช่ UPDATE)
        assert await conn.fetchval(
            """
            SELECT p.proname FROM pg_trigger t
            JOIN pg_proc p ON p.oid = t.tgfoid
            WHERE t.tgname = 'trg_notifications_stream'
            """
        ) == "notifications_stream_notify"
        # tgtype: bit 2 = INSERT · bit 1 = BEFORE (ต้องไม่ตั้ง = เป็น AFTER)
        tgtype = await conn.fetchval(
            "SELECT tgtype FROM pg_trigger WHERE tgname = 'trg_notifications_stream'"
        )
        assert tgtype & 4, "ต้องเป็น INSERT trigger"
        assert not (tgtype & 2), "ต้องเป็น AFTER ไม่ใช่ BEFORE"
        assert tgtype & 1, "ต้องเป็น FOR EACH ROW (สัญญาณต้องแยกตามผู้รับ)"

    # ใช้งานได้จริงหลัง migrate — พิสูจน์ด้วยสัญญาณจริง ไม่ใช่แค่มี object อยู่
    uid = stream_world["student"]["user_id"]
    listener, received = await _listen(test_db_url)
    try:
        await _notify_one(db_pool, uid)
        await _wait_events(received, 1)
        assert len(received) == 1
        assert json.loads(received[0]) == {"user_id": uid}
    finally:
        await listener.close()


@pytest.mark.asyncio
async def test_M2_notify_channel_matches_both_sides(stream_world, db_pool):
    """★ ชื่อช่องใน trigger (SQL literal) กับที่ hub ฟัง (`settings`) ต้องตรงกัน

    ชื่อช่องถูกเขียนเป็น **literal ใน SQL** (`pg_notify('piri_notifications', …)`)
    แต่ฝั่ง Python อ่านจาก `settings.NOTIFY_CHANNEL` — **ไม่มีอะไรผูกสองที่นี้เข้าด้วยกัน**
    ⇒ ถ้ามีใครแก้ `NOTIFY_CHANNEL` (เช่นตอนย้ายช่องแบบ blue/green) โดยไม่แก้ migration
    สัญญาณจะถูกส่งเข้าช่องที่ **ไม่มีใครฟัง** ⇒ badge กลับไปเงียบรอ poll 30 วิ
    โดยไม่มี error ที่ไหนเลย — **อาการเดียวกับที่ทั้งโมดูลนี้เกิดมาเพื่อแก้**

    ⚠️ D1/D4/D5/D7 จับ drift นี้ได้อยู่แล้ว (ผู้ฟังในเทสต์ใช้ `settings.NOTIFY_CHANNEL`)
       แต่ข้อความที่ได้คือ "ต้องได้ 1 สัญญาณ ขาด/เกิน = []" ซึ่งไม่บอกสาเหตุ
       ⇒ เทสต์นี้มีไว้ **บอกชื่อสาเหตุ** ไม่ใช่เพิ่มความครอบคลุม · และตรวจ **สองที่**:
       ที่ติดตั้งใน DB จริง (จับ "มีคนแก้ DB มือ") + ไฟล์ migration (จับ "ไฟล์ผิด")

    **mutation:** แก้ `NOTIFY_CHANNEL` ใน `core/config.py` ⇒ แตกทันทีพร้อมชื่อสาเหตุ
    """
    stream_world
    expected = f"'{settings.NOTIFY_CHANNEL}'"

    # ① สิ่งที่ติดตั้งจริงใน DB — คือสิ่งที่ตัดสินว่าสัญญาณไปถึงใคร
    installed = await db_pool.fetchval(
        "SELECT pg_get_functiondef(oid) FROM pg_proc "
        "WHERE proname = 'notifications_stream_notify'"
    )
    assert installed is not None, "ยังไม่ถูก migrate — ควรมี function นี้"
    assert expected in installed, (
        f"trigger ยิงเข้าช่องอื่น ไม่ใช่ {settings.NOTIFY_CHANNEL!r} — "
        "แก้ literal ใน migrations/020_notifications_pg_notify.py ให้ตรงกับ "
        "settings.NOTIFY_CHANNEL"
    )

    # ② ไฟล์ migration เอง — ไม่งั้นเครื่องที่ migrate ใหม่จะได้ช่องผิดทั้งที่ DB ตรง
    mig = importlib.import_module("migrations.020_notifications_pg_notify")
    with open(mig.__file__, encoding="utf-8") as f:
        assert expected in f.read(), "ไฟล์ migration กับ settings ไม่ตรงกัน"
