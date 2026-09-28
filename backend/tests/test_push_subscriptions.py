"""
🔔 Web Push — ปลายทาง + endpoint (A3)
=======================================
ไฟล์นี้ทดสอบ **ชั้น HTTP + ความปลอดภัย** ของการลงทะเบียนปลายทาง push
(ส่วน "ท่อ" ของการส่งอยู่ที่ `test_push_outbox.py`)

⚠️ **สามเทสต์ในไฟล์นี้คือด่านความปลอดภัย ไม่ใช่เทสต์ฟังก์ชัน** — ถ้าล้มแปลว่ามีช่อง
   ที่ผู้ใช้คนหนึ่งส่ง push ไปโผล่บนเครื่องของอีกคนได้:
     - **S3** ยึดเครื่องกับผู้ใช้ที่ล็อกอินอยู่ (login ใหม่บนเครื่องเดิม)
     - **S4** ลบได้เฉพาะปลายทางของตัวเอง
     - **S8** ปลอม `user_id` ใน body ไม่ได้
   ทั้งสามมาจากสถานการณ์จริงของโรงเรียน: **นักเรียนใช้มือถือร่วมกัน / เครื่องคอม
   ห้องสมุดเครื่องเดียวสลับกันล็อกอินหลายคน**

ตาม docs/rules/testing.md: ยืนยัน DB ตรง ๆ ผ่าน `db_pool` ไม่เชื่อ response
"""
import random

import pytest
import pytest_asyncio

from core.config import settings
from services import auth_service, push_service

PUSH_PATH = "/api/notifications/push"


# ============================================================
# Fixtures / helpers
# ============================================================

@pytest_asyncio.fixture
async def push_users(db_pool):
    """2 users ในห้องเดียวกัน — พอสำหรับเทสต์ "เครื่องเดียวกันสลับคน" """
    room_code = f"บ.{random.randint(1, 90)}"
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO rooms (room_code, room_name, level) VALUES ($1,$2,'ม.5')",
            room_code, room_code,
        )

    users = {}
    for label, no in [("a", 1), ("b", 2)]:
        sid = f"P{random.randint(1000, 9999)}{label.upper()}"
        uid = await auth_service.register_user(
            db_pool, sid, "1234", f"ผู้ใช้ {label}", sid, room_code, no, "student"
        )
        users[label] = {
            "user_id": uid,
            "token": auth_service.create_access_token(uid),
            "student_id": sid,
        }
    return users


@pytest.fixture(autouse=True)
def vapid_configured(monkeypatch):
    """ตั้งคีย์ VAPID — ไม่งั้น `enabled` เป็น false และเทสต์จะไม่ได้ทดสอบเส้นทางจริง

    ⚠️ บทเรียนจาก `test_push_outbox.py`: ตอนที่คีย์ว่าง เทสต์ 5 ตัวผ่านทั้งที่
       **ไม่ได้ทดสอบอะไรเลย** เพราะ `process_pending` / `get_status` ออกประตูแรก
       (คีย์ว่าง = ปิดทั้งระบบ) ก่อนถึงโค้ดที่ต้องการทดสอบ
    """
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", "test-public-key")
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "test-private-key")
    push_service._reset_vapid_cache()
    yield
    push_service._reset_vapid_cache()


def _auth(users, who="a"):
    return {"Authorization": f"Bearer {users[who]['token']}"}


def _endpoint(tag: str = "") -> str:
    return f"https://fcm.googleapis.com/fcm/send/{tag or random.randint(10**9, 10**10)}"


def _body(endpoint: str, p256dh: str = "BPabc_-def", auth: str = "authkey_-x"):
    return {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}


async def _rows(db_pool):
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            "SELECT user_id, endpoint, p256dh, auth, user_agent "
            "FROM push_subscriptions ORDER BY id"
        )


def _subscribe(client, users, *, who="a", endpoint=None, **kw):
    return client.post(
        f"{PUSH_PATH}/subscribe", json=_body(endpoint or _endpoint(), **kw),
        headers=_auth(users, who),
    )


def _status(client, users, who="a"):
    return client.get(f"{PUSH_PATH}/status", headers=_auth(users, who)).json()


# ============================================================
# 1) เส้นทางปกติ
# ============================================================

@pytest.mark.asyncio
async def test_S1_subscribe_registers_device(client, push_users, db_pool):
    """สมัครครั้งแรก → 200 · `device_count = 1` · **และมีแถวจริงใน DB ครบทุกคีย์**

    ⚠️ assert ระดับ DB ไม่ใช่แค่ response: ถ้า `save_subscription` คืนค่าโดยไม่เขียน
       (หรือเขียนคีย์ผิดคอลัมน์) response จะยังสวยเหมือนเดิม ⇒ push จะพังตอนส่งจริง
       ที่ worker ซึ่งไม่มีใครเห็น
    """
    endpoint = _endpoint()
    r = _subscribe(client, push_users, who="a", endpoint=endpoint,
                   p256dh="BPKEY_-x", auth="AUTHKEY_-y")

    assert r.status_code == 200, r.text
    assert r.json()["device_count"] == 1

    rows = await _rows(db_pool)
    assert len(rows) == 1
    assert rows[0]["user_id"] == push_users["a"]["user_id"]
    assert rows[0]["endpoint"] == endpoint
    assert rows[0]["p256dh"] == "BPKEY_-x"
    assert rows[0]["auth"] == "AUTHKEY_-y"


def test_S2_subscribe_twice_upserts_single_row(client, push_users):
    """สมัคร endpoint เดิมซ้ำ → **ยังมีแถวเดียว** และคีย์ใหม่ทับของเก่า

    mutation ที่ต้องทำให้แตก: ลบ `ON CONFLICT (endpoint) DO UPDATE` →
        ได้ `UniqueViolationError` → 500 (หรือ 2 แถวถ้าถอด unique index ด้วย)
    """
    endpoint = _endpoint()
    assert _subscribe(client, push_users, endpoint=endpoint, p256dh="OLD").status_code == 200
    r2 = _subscribe(client, push_users, endpoint=endpoint, p256dh="NEW")

    assert r2.status_code == 200, r2.text
    assert r2.json()["device_count"] == 1, "กดซ้ำแล้วได้อุปกรณ์เพิ่ม = ผู้ใช้ได้ push ซ้ำ"


def test_S3_claiming_endpoint_transfers_ownership(client, push_users):
    """★★ ด่านความปลอดภัย: user B สมัคร **endpoint เดิม** ของ A → เครื่องย้ายเป็นของ B

    🚨 สถานการณ์จริง: มือถือโรงเรียนเครื่องเดียว · A ล็อกอิน → เปิด push → ล็อกเอาต์
       → B ล็อกอินบนเครื่องเดิมแล้วเปิด push
       เบราว์เซอร์จะส่ง **endpoint เดิม** (subscription ผูกกับ *เบราว์เซอร์* ไม่ใช่ user)
       ⇒ ถ้า `ON CONFLICT` ไม่ยึดเจ้าของใหม่ **push ของ B จะไปโผล่บนเครื่องที่ยัง
         ล็อกอินค้างเป็น A** = ข้อมูลรั่วข้ามผู้ใช้

    mutation ที่ต้องทำให้แตก: ลบ `SET user_id = EXCLUDED.user_id` ออกจาก upsert
        → `user_id` ยังเป็นของ A (ยืนยันระดับแถวใน S3b)
    """
    endpoint = _endpoint()

    assert _subscribe(client, push_users, who="a", endpoint=endpoint).status_code == 200
    r = _subscribe(client, push_users, who="b", endpoint=endpoint)

    assert r.status_code == 200, r.text
    assert r.json()["device_count"] == 1
    # A ต้องไม่เหลืออุปกรณ์แล้ว — ไม่งั้นเท่ากับ push ไปถึงสองคนจากเครื่องเดียว
    assert _status(client, push_users, "a")["device_count"] == 0, (
        "เครื่องย้ายไปเป็นของ B แล้ว A ต้องไม่เหลือ"
    )


@pytest.mark.asyncio
async def test_S3b_ownership_transfer_row_level(client, push_users, db_pool):
    """S3 ในระดับแถว — พิสูจน์ว่า **มีแถวเดียว** และ `user_id` เป็นของ B จริง"""
    endpoint = _endpoint()
    _subscribe(client, push_users, who="a", endpoint=endpoint)
    _subscribe(client, push_users, who="b", endpoint=endpoint)

    rows = await _rows(db_pool)
    assert len(rows) == 1, f"ต้องมีแถวเดียว (endpoint เดียว) แต่ได้ {len(rows)}"
    assert rows[0]["user_id"] == push_users["b"]["user_id"], (
        "🚨 เจ้าของไม่ถูกยึดใหม่ ⇒ push ของ B จะไปโผล่บนเครื่องที่ล็อกอินค้างเป็น A"
    )


def test_S4_unsubscribe_only_removes_own_endpoint(client, push_users):
    """★★ ด่านความปลอดภัย: B ส่ง unsubscribe ด้วย endpoint ของ A → ของ A ต้องอยู่ต่อ

    🚨 ถ้า `DELETE` ไม่มี `AND user_id = $1` ผู้ใช้คนใดก็ลบปลายทางของคนอื่นได้
       เพียงรู้ endpoint (ซึ่งรั่วได้ทาง log/proxy/หน้าจอ debug)
       ⇒ **ปิดการแจ้งเตือนของเหยื่อเงียบ ๆ** ซึ่งเป็นการกลั่นแกล้งที่เกิดได้จริง

    ⚠️ **endpoint ของ B ต้องมีอยู่จริง** เพื่อให้ความล้มเหลวมาจาก `user_id` ไม่ใช่จาก
       "ไม่มีแถวเลย" — ไม่งั้นเทสต์จะผ่านเพราะเหตุผลผิด (และจะไม่จับ mutation)

    mutation ที่ต้องทำให้แตก: ลบ `AND user_id = $1` → ของ A หาย
    """
    endpoint_a = _endpoint("A")
    endpoint_b = _endpoint("B")
    _subscribe(client, push_users, who="a", endpoint=endpoint_a)
    _subscribe(client, push_users, who="b", endpoint=endpoint_b)

    r = client.post(f"{PUSH_PATH}/unsubscribe", json={"endpoint": endpoint_a},
                    headers=_auth(push_users, "b"))

    assert r.status_code == 200, r.text
    assert r.json()["removed"] == 0, "B ลบของ A ได้ ⇒ ช่องโหว่"
    assert r.json()["device_count"] == 1, "อุปกรณ์ของ B ต้องไม่ถูกแตะ"
    assert _status(client, push_users, "a")["device_count"] == 1, (
        "🚨 ปลายทางของ A ถูกคนอื่นลบ"
    )


def test_S5_unsubscribe_is_idempotent(client, push_users):
    """ลบซ้ำ → ครั้งที่สอง `removed = 0` และ **ไม่ error (ไม่ใช่ 404)**

    เพราะ "ลบสิ่งที่ไม่มีอยู่" = ผลลัพธ์ที่ client ต้องการแล้ว · และเบราว์เซอร์
    อาจ unsubscribe ไปเองก่อนถึงที่นี่ (เช่นผู้ใช้กดล้างข้อมูลเว็บไซต์)
    """
    endpoint = _endpoint()
    _subscribe(client, push_users, endpoint=endpoint)

    first = client.post(f"{PUSH_PATH}/unsubscribe", json={"endpoint": endpoint},
                        headers=_auth(push_users))
    second = client.post(f"{PUSH_PATH}/unsubscribe", json={"endpoint": endpoint},
                         headers=_auth(push_users))

    assert first.json()["removed"] == 1
    assert second.status_code == 200
    assert second.json()["removed"] == 0
    assert second.json()["device_count"] == 0


# ============================================================
# 2) Validation + ความปลอดภัยของ identity
# ============================================================

@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/x",    # scheme ผิด
        "ftp://example.com/x",
        "https:/fcm.googleapis.com/x",    # พิมพ์สแลชขาด — จริง ๆ คือ relative path
        "fcm.googleapis.com/x",           # ไม่มี scheme
        "",                               # ว่าง → ตกที่ min_length=8
    ],
)
def test_S6_non_https_endpoint_is_rejected(client, push_users, endpoint):
    """endpoint ที่ไม่ใช่ `https://` → **422** (ไม่ปล่อยผ่านไปพังใน worker)

    ⚠️ ถ้าปล่อยผ่าน จะไปล้มตอนส่งจริงด้วย error จากผู้ให้บริการ ซึ่ง **มองไม่เห็น
       จากฝั่งเราเลย** (worker ไม่มีใครอ่าน response) ⇒ ต้องจับที่ทางเข้า
       และเบราว์เซอร์ทุกตัวให้ endpoint เป็น `https://` อยู่แล้ว ⇒ ค่าที่ไม่ใช่
       แปลว่ามีอะไรผิดปกติหรือมีคนยิง API ตรง ไม่ใช่ผู้ใช้พิมพ์ผิด

    mutation ที่ต้องทำให้แตก: ลบ `_https_only` validator → ได้ 200
    """
    r = client.post(f"{PUSH_PATH}/subscribe",
                    json=_body(endpoint), headers=_auth(push_users))
    assert r.status_code == 422, f"{endpoint!r} ควรถูกปฏิเสธ แต่ได้ {r.status_code}"


@pytest.mark.parametrize("keys", [
    {"p256dh": "", "auth": "x"},
    {"p256dh": "x", "auth": ""},
    {},
])
def test_S6b_empty_or_missing_keys_rejected(client, push_users, keys):
    """คีย์ว่าง/ขาด → 422 · ไม่มีคีย์ก็ไม่มีทางเข้ารหัสส่งได้จริง"""
    r = client.post(f"{PUSH_PATH}/subscribe",
                    json={"endpoint": _endpoint(), "keys": keys},
                    headers=_auth(push_users))
    assert r.status_code == 422


@pytest.mark.parametrize("path", ["status", "subscribe", "unsubscribe"])
def test_S7_requires_login(client, path):
    """ไม่มี token → **401** (ไม่ใช่ 500 และไม่ใช่ 200)"""
    if path == "status":
        r = client.get(f"{PUSH_PATH}/status")
    else:
        r = client.post(f"{PUSH_PATH}/{path}", json=_body(_endpoint()))
    assert r.status_code == 401, f"{path} ได้ {r.status_code} แทนที่จะเป็น 401"


@pytest.mark.parametrize("path", ["status", "subscribe", "unsubscribe"])
def test_S7b_api_key_system_call_is_401(client, path):
    """`X-API-Key` (system RPC) → **401** เพราะไม่มี "ตัวตน" ให้ผูกปลายทาง

    ⚠️ `get_current_user` คืน `{"user_id": None}` สำหรับ API key (ไม่ throw) ⇒
       **`_ensure_user()` คือด่านเดียวที่กันไว้** · ผลถ้าถอดด่านนี้ออก ต่างกัน 2 แบบ:
         - `subscribe` / `unsubscribe` → เขียน `user_id = NULL` → FK violation → **500**
           (อาการสับสนที่แพง: ดูเหมือนฐานข้อมูลพัง ทั้งที่แค่ไม่ได้ล็อกอิน)
         - `status` → **200** พร้อม `device_count: 0` ซึ่งแย่กว่า 500 เสียอีก เพราะ
           ดูเหมือนสำเร็จ — frontend จะโชว์ "ยังไม่มีอุปกรณ์" ให้ผู้เรียกที่ไม่มีตัวตน

    ℹ️ เทสต์ S7 (ไม่มี header เลย) **ไม่จับ mutation นี้** — มันล้มที่ชั้น dependency
       (`get_current_user` โยน 401 เอง) ก่อนถึงบรรทัดนี้ ⇒ **S7b คือเทสต์ที่รับน้ำหนัก**
       (พิสูจน์แล้ว: ถอด `_ensure_user` → S7b ล้ม 3/3 · S7 ยังผ่าน)

    mutation ที่ต้องทำให้แตก: ถอด `_ensure_user` → ได้ 500 (2 ตัว) + 200 (status)
    """
    hdr = {"X-API-Key": settings.API_KEY}
    if path == "status":
        r = client.get(f"{PUSH_PATH}/status", headers=hdr)
    else:
        r = client.post(f"{PUSH_PATH}/{path}", json=_body(_endpoint()), headers=hdr)
    assert r.status_code == 401, f"{path} ได้ {r.status_code} แทนที่จะเป็น 401"


@pytest.mark.asyncio
async def test_S8_body_cannot_forge_user_id(client, push_users, db_pool):
    """★★★ ด่านความปลอดภัย: ส่ง `user_id` ของคนอื่นมาใน body → **ต้องถูกเมิน**

    🚨 ถ้า schema รับ `user_id` ผู้โจมตีก็ลงทะเบียน **อุปกรณ์ของตัวเอง** ให้เป็นของ
       เหยื่อ ⇒ **push ทุกอันของเหยื่อ (รวมเนื้อหาเรื่องร้องเรียน) ถูกส่งไปที่อุปกรณ์
       ของผู้โจมตี** — ช่องที่ร้ายแรงที่สุดของ A3

    ⭐ pydantic ตัดฟิลด์แปลกปลอมทิ้งโดย default ⇒ เทสต์นี้ *verifies ว่าพฤติกรรมนั้น
       ยังจริงอยู่* และจะล้มทันทีถ้ามีคนเพิ่ม `user_id` เข้า schema ในอนาคต
       (การป้องกันที่ "โดยบังเอิญ" ต้องมีเทสต์ล็อกไว้ ไม่งั้นวันหนึ่งจะมีคน
        "ปรับปรุง" schema ให้รับ field นี้เพื่อความสะดวก)

    mutation ที่ต้องทำให้แตก: เพิ่ม `user_id: Optional[int] = None` เข้า
        `PushSubscriptionIn` แล้ว router ใช้ค่านั้น → แถวจะเป็นของเหยื่อ
    """
    victim_id = push_users["a"]["user_id"]

    r = client.post(
        f"{PUSH_PATH}/subscribe",
        json={**_body(_endpoint()), "user_id": victim_id},   # ← พยายามปลอม
        headers=_auth(push_users, "b"),
    )
    assert r.status_code == 200, r.text

    rows = await _rows(db_pool)
    assert len(rows) == 1
    assert rows[0]["user_id"] == push_users["b"]["user_id"], (
        "🚨 ปลอม user_id ได้ ⇒ push ของเหยื่อจะถูกส่งไปที่อุปกรณ์ของผู้โจมตี"
    )


# ============================================================
# 3) สถานะ / สวิตช์ปิดฉุกเฉิน
# ============================================================

def test_S9_status_counts_only_own_devices(client, push_users):
    """สถานะคืน public key จริง + จำนวนอุปกรณ์ของ **ตัวเองเท่านั้น**"""
    _subscribe(client, push_users, who="a")
    _subscribe(client, push_users, who="b")

    a = _status(client, push_users, "a")
    assert a["enabled"] is True
    assert a["public_key"] == settings.VAPID_PUBLIC_KEY
    assert a["device_count"] == 1, "เห็นอุปกรณ์ของคนอื่นด้วย ⇒ รั่ว"


def test_S10_status_disabled_when_no_vapid_key(client, push_users, monkeypatch):
    """ไม่มีคีย์ VAPID → `enabled=false` และ **public_key ต้องเป็นค่าว่าง**

    ⭐ นี่คือสวิตช์ปิดฉุกเฉินที่ไม่ต้อง deploy (ลบคีย์จาก `.env` + force update)
       ⚠️ ห้ามส่งคีย์ออกไปทั้งที่ปิดใช้งาน — frontend ใช้ `enabled` ตัดสินใจซ่อนการ์ด
          แต่ถ้าส่งคีย์มาด้วย จะมีคนเอาไป subscribe ต่อแล้วได้ error ที่อธิบายไม่ตรง

    mutation ที่ต้องทำให้แตก: คืน `settings.VAPID_PUBLIC_KEY` เสมอ → key ไม่ว่าง
    """
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", "")
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "")

    body = _status(client, push_users, "a")
    assert body["enabled"] is False
    assert body["public_key"] == ""
