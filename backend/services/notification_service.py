"""
🔔 ระบบแจ้งเตือน (Notifications) — unread badge + read-receipt
=============================================================
- ทุก write ที่สำคัญจะ insert notification แถวใน transaction เดียวกับข้อมูลหลัก
  (ลอกแบบ AuditLogger — ตามกฎ backend.md) ผ่าน notify()/notify_bulk()/notify_fanout()
- group_type ใช้สร้าง badge ตามเมนู: issue_mine (เรื่องของฉัน) / issue_received (เรื่องที่รับ)
  / board (PIRI Boards) / report (จัดการรายงาน)
- read_at NULL = ยังไม่อ่าน → badge = COUNT(*) WHERE read_at IS NULL GROUP BY group_type
- เปิดหน้ารายละเอียด (เรื่อง/บอร์ด/รายงาน) → mark_read → badge ลดลง

ทุกฟังก์ชันรับ `conn` ที่อยู่ใน transaction ของ caller (ไม่เปิด transaction เอง)

🔔 **Web Push (A3) แขวนอยู่ที่ trigger ของ DB ไม่ใช่ที่ไฟล์นี้** — ทุกแถวที่ insert เข้า `notifications`
จะถูก `trg_notifications_push_outbox` (migration 018) คัดลอกลง `push_outbox` ให้อัตโนมัติ
⇒ ที่นี่ **ไม่มีโค้ด push เลยแม้บรรทัดเดียว** และไม่ควรมี · เพิ่ม/แก้คิวรีที่ insert notification
ต้องผ่าน `notify*` เสมอ ไม่งั้นแถวนั้นจะไม่ถูก push (ดู `services/push_service.py` ฝั่งส่ง)
"""
from typing import Iterable, List, Optional

from core.exceptions import ValidationError

# กลุ่ม badge ตามเมนู (เรียงตาม GROUP_TABS ใน frontend)
#
# ⚠️ **สองลิสต์นี้ต่างกันโดยเจตนา — อย่ารวมเป็นตัวเดียว:**
#   · GROUP_TYPES      = ทุกกลุ่มที่ *ปรากฏได้* ในตาราง notifications (ใช้ zero-fill badge)
#   · PREFERENCE_GROUPS = กลุ่มที่ผู้ใช้ *ปิดได้* (ใช้ zero-fill หน้าตั้งค่า + เป็น pattern ของ PUT)
# `announcement` (E2 ประกาศฉุกเฉิน) อยู่ในลิสต์บนเท่านั้น ⇒ **ปิดไม่ได้โดยเจตนา**
#   ประกาศฉุกเฉินที่เงียบได้ = ประกาศที่ล้มเหลวในหน้าที่ของมัน · ผู้ใช้ยังปิด *กลุ่มอื่น* ได้ตามเดิม
#   และการที่มันไม่อยู่ใน PREFERENCE_GROUPS ทำให้ `_pref_allows` คืน True เสมอ (ไม่มีแถว = เปิด)
# `event` (D1 กิจกรรม) อยู่ **ทั้งสองลิสต์** — ต่างจาก `announcement` เพราะกิจกรรม
#   ไม่ใช่เรื่องฉุกเฉิน ⇒ ผู้ใช้ที่ไม่อยากได้ข่าวกิจกรรมต้องปิดได้ ไม่งั้นสภาเปิดรับสมัคร
#   สัปดาห์ละหลายกิจกรรมจะกลายเป็นสแปมที่ปิดไม่ได้ (และเป็นข้อร้องเรียนที่แก้ไม่ได้เลย)
GROUP_TYPES = ("issue_mine", "issue_received", "board", "report", "announcement", "event")
PREFERENCE_GROUPS = ("issue_mine", "issue_received", "board", "report", "event")


# ============================================================
# ⚙️ Preference gate — ผู้ใช้ปิดกลุ่มไหนไว้?
# ============================================================
# "ไม่มีแถว" = เปิด (ค่าตั้งต้นของทุกคน — ไม่ต้อง backfill)
# ⚠️ ทั้ง 3 ฟังก์ชัน notify* ต้องผ่าน gate นี้เสมอ ไม่งั้นคนที่ปิดไว้จะยังโดนแจ้งเตือน
#    ถ้าเพิ่มคิวรีที่ insert notification เองในอนาคต ต้องเรียก gate เองด้วย

async def _pref_allows(conn, user_id: int, group_type: str) -> bool:
    """ผู้ใช้รายนี้ยังเปิดรับกลุ่มนี้อยู่ไหม (ใช้กับ notify ที่มีผู้รับคนเดียว)"""
    val = await conn.fetchval(
        "SELECT enabled FROM notification_preferences WHERE user_id = $1 AND group_type = $2",
        user_id, group_type,
    )
    return True if val is None else bool(val)


async def _filter_allowed(conn, user_ids: List[int], group_type: str) -> List[int]:
    """กรองผู้ที่ปิดกลุ่มนี้ออก — ยิงคิวรีเดียว ไม่ใช่ N คิวรี"""
    if not user_ids:
        return []
    blocked = await conn.fetch(
        """
        SELECT user_id FROM notification_preferences
        WHERE group_type = $1 AND enabled = FALSE AND user_id = ANY($2::int[])
        """,
        group_type, list(user_ids),
    )
    blocked_ids = {r["user_id"] for r in blocked}
    return [u for u in user_ids if u not in blocked_ids]


# ============================================================
# ✍️ Write helpers — เรียกภายใน transaction ของ caller
# ============================================================

async def notify(
    conn,
    *,
    user_id: int,
    group_type: str,
    type: str,
    title: str,
    body: str,
    entity_type: str,
    entity_id: int,
    board_id: Optional[int] = None,
    actor_id: Optional[int] = None,
    actor_name: Optional[str] = None,
    bypass_quiet_hours: bool = False,
) -> None:
    """สร้าง notification 1 แถว (skip ถ้า actor ทำกับตัวเอง — ไม่สแปมตัวเอง
    และ skip ถ้าผู้รับปิดกลุ่มนี้ไว้)

    `bypass_quiet_hours` (A8/E2) = ธงติดมากับ **แถว** ไม่ใช่กับผู้รับ ⇒ ใช้กับประกาศฉุกเฉิน
    ที่ต้องถึงมือแม้โรงเรียนเปิดช่วงเวลาไม่ส่งแจ้งเตือน · ค่าตั้งต้น False = ถูก quiet hours
    กลั้นตามปกติ (ด่านจริงอยู่ที่ `push_service.process_pending` ตอน *ส่ง* ไม่ใช่ตอน insert)"""
    if actor_id is not None and int(actor_id) == int(user_id):
        return
    if not await _pref_allows(conn, user_id, group_type):
        return
    await conn.execute(
        """
        INSERT INTO notifications
            (user_id, group_type, type, title, body, entity_type, entity_id,
             board_id, actor_id, actor_name, bypass_quiet_hours)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """,
        user_id, group_type, type, title, body, entity_type, entity_id,
        board_id, actor_id, actor_name, bypass_quiet_hours,
    )


async def notify_bulk(
    conn,
    user_ids: Iterable[int],
    *,
    group_type: str,
    type: str,
    title: str,
    body: str,
    entity_type: str,
    entity_id: int,
    board_id: Optional[int] = None,
    actor_id: Optional[int] = None,
    actor_name: Optional[str] = None,
    bypass_quiet_hours: bool = False,
) -> None:
    """หลายผู้รับในคราวเดียว (filter actor ออกก่อน insert แล้วกรองคนที่ปิดกลุ่มนั้น)

    `bypass_quiet_hours` ติดไปกับ **ทุกแถว** ที่สร้างในครั้งนี้ (ดู `notify`)"""
    ids = [
        u for u in {int(x) for x in user_ids}
        if actor_id is None or int(u) != int(actor_id)
    ]
    ids = await _filter_allowed(conn, ids, group_type)
    if not ids:
        return
    await conn.executemany(
        """
        INSERT INTO notifications
            (user_id, group_type, type, title, body, entity_type, entity_id,
             board_id, actor_id, actor_name, bypass_quiet_hours)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """,
        [
            (uid, group_type, type, title, body, entity_type, entity_id,
             board_id, actor_id, actor_name, bypass_quiet_hours)
            for uid in ids
        ],
    )


async def notify_fanout(
    conn,
    *,
    group_type: str,
    type: str,
    title: str,
    body: str,
    entity_type: str,
    entity_id: int,
    board_id: Optional[int] = None,
    actor_id: Optional[int] = None,
    actor_name: Optional[str] = None,
    bypass_quiet_hours: bool = False,
) -> None:
    """Fan-out ไปทุก active user (ตาราง students) — ขนาดโรงเรียนไม่กี่ร้อย/พันคน OK
    ใน transaction เดียว (ถ้า >10k คนค่อยย้ายไป queue ตามแผน)

    กรองคนที่ปิดกลุ่มนี้ใน SQL เลย (ไม่ดึงออกมา filter ใน Python) — $1 คือ group_type
    ⚠️ `students.user_id` เขียน qualified เพราะใน WHERE มี subquery ที่มีคอลัมน์ user_id ของตัวเอง

    `bypass_quiet_hours` ติดไปกับทุกแถว (E2: ประกาศฉุกเฉินต้องทะลุ quiet hours)
    ⚠️ `NOT EXISTS` ด้านล่างเป็น no-op โดยธรรมชาติเมื่อ `group_type='announcement'` เพราะ
       `PREFERENCE_GROUPS` ไม่มีค่านั้น ⇒ ไม่มีทางมีแถว preference ของกลุ่มนี้อยู่เลย
       (ไม่ต้อง special-case — แต่ **อย่า** เผลอเพิ่ม 'announcement' เข้า PREFERENCE_GROUPS)"""
    await conn.execute(
        """
        INSERT INTO notifications
            (user_id, group_type, type, title, body, entity_type, entity_id,
             board_id, actor_id, actor_name, bypass_quiet_hours)
        SELECT DISTINCT students.user_id, $1::varchar, $2::varchar, $3::text, $4::text, $5::varchar,
               $6::int, $7::int, $8::int, $9::text, $10::boolean
        FROM students
        WHERE deleted_at IS NULL AND status = 'active'
          AND ($8::int IS NULL OR students.user_id <> $8)
          AND NOT EXISTS (
              SELECT 1 FROM notification_preferences p
              WHERE p.user_id = students.user_id
                AND p.group_type = $1
                AND p.enabled = FALSE
          )
        """,
        group_type, type, title, body, entity_type, entity_id,
        board_id, actor_id, actor_name, bypass_quiet_hours,
    )


# ============================================================
# 👥 Receiver helpers — ผู้รับตามระดับ (ใช้ภายใน transaction hook)
# ============================================================

async def _room_receiver_ids(conn, room_id: int) -> List[int]:
    """หัวหน้าห้อง + รอง 4 ฝ่าย ในห้องนั้น (ทุกคนถือ RECEIVE_ISSUES)"""
    rows = await conn.fetch(
        """
        SELECT user_id FROM students
        WHERE room_id = $1 AND deleted_at IS NULL AND status = 'active'
          AND class_role IN ('class_president','vice_academic','vice_discipline','vice_activity','vice_reception')
        """,
        room_id,
    )
    return [r["user_id"] for r in rows]


async def _council_ids(conn) -> List[int]:
    """สภานักเรียน/ประธานสภา/ครูสภา + admin (DISTINCT กันคนมีหลายห้อง)"""
    rows = await conn.fetch(
        """
        SELECT DISTINCT user_id FROM students
        WHERE deleted_at IS NULL AND status = 'active'
          AND (is_admin = TRUE OR class_role IN ('council_member','council_president','teacher_council'))
        """
    )
    return [r["user_id"] for r in rows]


async def _level_president_ids(conn, level: str) -> List[int]:
    """ประธานระดับของระดับชั้น (rooms.level = ระดับของเรื่อง)"""
    rows = await conn.fetch(
        """
        SELECT s.user_id FROM students s
        JOIN rooms r ON r.id = s.room_id
        WHERE s.class_role IN ('level_president', 'level_vice_president')
          AND s.deleted_at IS NULL AND s.status = 'active'
          AND r.level = $1 AND r.deleted_at IS NULL
        """,
        level,
    )
    return [r["user_id"] for r in rows]


async def _user_display_name(conn, user_id: int) -> Optional[str]:
    """ชื่อแสดง (prefix+first+last จาก students / fallback users.full_name)"""
    c = await conn.fetchrow(
        """
        SELECT NULLIF(TRIM(CONCAT_WS(' ', s.prefix, s.first_name, s.last_name)), '') AS student_name,
               u.full_name
        FROM students s
        JOIN users u ON u.id = s.user_id
        WHERE s.user_id = $1 AND s.deleted_at IS NULL AND s.status = 'active'
        ORDER BY s.id LIMIT 1
        """,
        user_id,
    )
    return (c["student_name"] or c["full_name"]) if c else None


def _mask_actor(reporter_name: Optional[str], is_anonymous: bool) -> Optional[str]:
    """ไม่รั่วชื่อผู้แจ้งถ้าเรื่องเป็น anonymous"""
    return "ไม่ระบุชื่อ" if is_anonymous else reporter_name


# ============================================================
# 📖 Read + mark-read
# ============================================================

async def get_unread_counts(pool, user_id: int) -> dict:
    """badge = unread notification ต่อกลุ่ม (index เร็ว, sub-ms)"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT group_type, COUNT(*)::int AS cnt
            FROM notifications
            WHERE user_id = $1 AND read_at IS NULL
            GROUP BY group_type
            """,
            user_id,
        )
    counts = {r["group_type"]: r["cnt"] for r in rows}
    for g in GROUP_TYPES:
        counts.setdefault(g, 0)
    return {"counts": counts, "total": sum(counts.values())}


async def get_preferences(pool, user_id: int) -> dict:
    """ค่าตั้งค่าการแจ้งเตือนของฉัน — **คืนครบทุกกลุ่มที่ปิดได้เสมอ** (กลุ่มที่ไม่มีแถว = เปิด)

    zero-fill แบบเดียวกับ get_unread_counts: frontend ไม่ต้องรู้จักรายชื่อกลุ่มเอง
    ⇒ วันหน้าเพิ่มกลุ่มใหม่ แค่แก้ PREFERENCE_GROUPS ที่เดียว UI ก็ได้แถวใหม่อัตโนมัติ

    ⚠️ ใช้ `PREFERENCE_GROUPS` (5) **ไม่ใช่** `GROUP_TYPES` (6) — `announcement` ต้องไม่โผล่
    เป็นสวิตช์ที่ปิดได้ (ดูเหตุผลที่หัวไฟล์) · ถ้าเผลอเปลี่ยนเป็น GROUP_TYPES เมื่อไหร่
    UI จะขึ้นสวิตช์ "ประกาศฉุกเฉิน" ที่กดปิดได้ทันที = ความสามารถในการปิดประกาศฉุกเฉิน
    ซึ่งเป็นสิ่งที่งานนี้ตั้งใจไม่ให้มี"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT group_type, enabled FROM notification_preferences WHERE user_id = $1",
            user_id,
        )
    saved = {r["group_type"]: r["enabled"] for r in rows}
    return {
        "preferences": [
            {"group_type": g, "enabled": bool(saved.get(g, True))}
            for g in PREFERENCE_GROUPS
        ]
    }


async def update_preferences(pool, user_id: int, items: List[dict]) -> dict:
    """อัปเดตเฉพาะกลุ่มที่ส่งมา (upsert) แล้วคืนค่าล่าสุดทั้งชุด

    - เป็น **partial update** — กลุ่มที่ไม่ส่งมาคงค่าเดิม (ไม่ reset เป็นเปิด)
    - ⚠️ **ไม่เขียน audit log โดยเจตนา** — เป็นค่าส่วนตัว ไม่ใช่ state ที่แชร์
      และจะทำให้ `audit_logs` เสียงดังโดยไม่จำเป็น
    - เปิด transaction เอง (ต่างจาก notify* ที่รับ conn จาก caller)"""
    # dedupe: ถ้าส่ง group_type เดิมมาสองครั้ง ให้ตัวหลังชนะ — กัน
    # "ON CONFLICT DO UPDATE command cannot affect row a second time"
    deduped = {it["group_type"]: it["enabled"] for it in items}
    if not deduped:
        return await get_preferences(pool, user_id)

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(
                """
                INSERT INTO notification_preferences (user_id, group_type, enabled)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, group_type)
                DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = NOW()
                """,
                [(user_id, g, enabled) for g, enabled in deduped.items()],
            )
    return await get_preferences(pool, user_id)


def _to_dict(r) -> dict:
    return {
        "id": r["id"],
        "group_type": r["group_type"],
        "type": r["type"],
        "title": r["title"],
        "body": r["body"],
        "entity_type": r["entity_type"],
        "entity_id": r["entity_id"],
        "board_id": r["board_id"],
        "actor_id": r["actor_id"],
        "actor_name": r["actor_name"],
        "read_at": r["read_at"],
        "created_at": r["created_at"],
    }


async def list_notifications(
    pool,
    user_id: int,
    *,
    group_type: Optional[str] = None,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """รายการแจ้งเตือนของฉัน (ล่าสุดก่อน) — envelope {items,total,page,page_size,pages}"""
    async with pool.acquire() as conn:
        where = ["user_id = $1"]
        params: list = [user_id]
        if group_type:
            params.append(group_type)
            where.append(f"group_type = ${len(params)}")
        if unread_only:
            where.append("read_at IS NULL")
        where_sql = " AND ".join(where)

        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM notifications WHERE {where_sql}", *params
        )
        rows = await conn.fetch(
            f"""
            SELECT * FROM notifications
            WHERE {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """,
            *params, limit, offset,
        )
    return {
        "items": [_to_dict(r) for r in rows],
        "total": total,
        "page": offset // limit + 1 if limit else 1,
        "page_size": limit,
        "pages": (total + limit - 1) // limit if limit and total else 0,
    }


async def mark_read(
    pool,
    user_id: int,
    *,
    ids: Optional[List[int]] = None,
    group_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    board_id: Optional[int] = None,
    all_: bool = False,
) -> int:
    """Mark อ่าน — ยืดหยุ่น: ids | group_type | entity_type(+entity_id) | board_id | read_all
    ⚠️ ถ้าไม่มี criteria เลยและไม่ใช่ read_all → 400 (กันเผลอเคลียร์ทุกอย่าง)"""
    if not all_ and not (ids or group_type or entity_type or entity_id is not None or board_id is not None):
        raise ValidationError("ระบุเงื่อนไขการอ่าน (ids/group_type/entity/board_id) หรือ read_all")

    async with pool.acquire() as conn:
        where = ["user_id = $1", "read_at IS NULL"]
        params: list = [user_id]
        if not all_:
            if ids:
                params.append(list(ids))
                where.append(f"id = ANY(${len(params)}::int[])")
            if group_type:
                params.append(group_type)
                where.append(f"group_type = ${len(params)}")
            if entity_type:
                params.append(entity_type)
                where.append(f"entity_type = ${len(params)}")
            if entity_id is not None:
                params.append(entity_id)
                where.append(f"entity_id = ${len(params)}")
            if board_id is not None:
                params.append(board_id)
                where.append(f"board_id = ${len(params)}")
        return await conn.fetchval(
            f"""
            WITH updated AS (
                UPDATE notifications SET read_at = NOW()
                WHERE {" AND ".join(where)}
                RETURNING id
            )
            SELECT COUNT(*) FROM updated
            """,
            *params,
        )
