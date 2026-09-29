"""บันทึกไว้อ่านทีหลัง (C2) — ชุดส่วนตัวของเจ้าของบัญชีเท่านั้น

**ไม่ต้องมี `require_permission`** — ตัวตนคือสิทธิ์ (แบบเดียวกับ `me_service`)
⇒ `user_id` มาจาก JWT เสมอ และ **ทุกคิวรีต้องมี `user_id` อยู่ใน WHERE**
   (นี่คือด่านความปลอดภัยเดียวของตารางนี้ — ไม่มี RLS ไม่มี FK ผูกกับเจ้าของ)

⚠️ **ทำไมไม่เขียน audit log** — เป็นค่าส่วนตัว ไม่ใช่ state ที่แชร์
   ตัดสินแบบเดียวกับ `notification_service.update_preferences` (ดู plan §22.2)
   และจะทำให้ `audit_logs` เสียงดังโดยไม่มีใครได้ประโยชน์

⭐ **`bookmark` คือ set membership ไม่ใช่การลงคะแนน** ⇒ `create` ต้อง **idempotent**
   กดซ้ำ/ดับเบิลแท็ป/เน็ตช้า ต้องไม่ error — ต่างจาก `piri_votes` ที่ใช้ `ConflictError`
   เพราะที่นั่น "หนึ่งเสียง" มีความหมายจริง (plan §22.2 ข้อ 3)
"""
from typing import Optional, Tuple

import asyncpg

from core.exceptions import NotFoundError

# ตรวจว่า entity มีจริง+ไม่ถูกลบก่อนบันทึก — **whitelist แบบ dict ไม่ใช่ f-string**
# ⚠️ ห้ามเปลี่ยนเป็น f-string ที่ต่อชื่อตารางจาก `entity_type` เด็ดขาด
#    ถึงแม้ router จะ validate ด้วย Literal แล้ว ก็ไม่ควรมีทางที่ค่าจากผู้ใช้จะกลายเป็น SQL
_EXISTS_SQL = {
    "issue": "SELECT id FROM issues WHERE id = $1 AND deleted_at IS NULL",
    # ⚠️ บอร์ด "เปิดไม่ได้" มีสองทาง: `deleted_at` (ลบ) และ `status = 'hidden'` (สภากดซ่อน)
    #    `get_board_detail()` 404 ทั้งคู่ ⇒ บันทึกไปก็เปิดดูไม่ได้ ⇒ ปฏิเสธตั้งแต่ตอนบันทึก
    #    (สัญญาเดียวกับ B4 ที่ใช้ `deleted_at`) · ห้ามใช้ `status <> 'active'` —
    #    `'closed'` ยังเปิดดูได้ ⇒ จะปฏิเสธของที่ดูได้จริง
    "board": (
        "SELECT id FROM piri_boards"
        " WHERE id = $1 AND deleted_at IS NULL AND status <> 'hidden'"
    ),
}


def _checked(entity_type: str) -> str:
    """ยืนยันว่าชนิดนี้รู้จัก — กัน KeyError กลายเป็น 500 ถ้ามีคนเพิ่ม Literal แล้วลืมเพิ่ม SQL"""
    if entity_type not in _EXISTS_SQL:
        raise NotFoundError(f"ไม่รู้จักชนิด '{entity_type}'")
    return entity_type


async def list_bookmarks(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    entity_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """รายการที่บันทึกไว้ (ล่าสุดก่อน) — envelope เดียวกับ `list_notifications`

    ⭐ **LEFT JOIN ไม่ใช่ INNER JOIN โดยเจตนา** — ถ้าเรื่อง/บอร์ดถูกลบ (soft)
       bookmark ต้อง **ยังอยู่ในลิสต์** พร้อม `is_deleted_source = true`
       ถ้าใช้ INNER JOIN แถวนั้นจะหายไปเงียบ ๆ แล้วผู้ใช้จะถามว่า "ที่บันทึกไว้หายไปไหน"
       (สัญญาเดียวกับ `is_deleted_source` ฝั่ง frontend — `types/bookmark.ts`)

    ⚠️ **join ไม่กรอง `deleted_at IS NULL`** — เราต้องการให้แถวที่ถูกลบ *ยัง join ได้*
       เพื่อเอา `title` จริงมาแสดง แล้วค่อยบอกว่า "ต้นทางถูกลบแล้ว" ที่ `is_deleted_source`
       ⇒ เงื่อนไข `deleted_at` อยู่ใน `CASE` ไม่ใช่ใน `ON`
    """
    where = ["b.user_id = $1"]
    params: list = [user_id]
    if entity_type:
        _checked(entity_type)
        params.append(entity_type)
        where.append(f"b.entity_type = ${len(params)}")
    where_sql = " AND ".join(where)

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM bookmarks b WHERE {where_sql}", *params
        )
        rows = await conn.fetch(
            f"""
            SELECT b.id, b.entity_type, b.entity_id, b.created_at,
                   COALESCE(i.title, pb.title, '(ต้นทางถูกลบแล้ว)') AS title,
                   LEFT(COALESCE(i.description, pb.description), 160) AS excerpt,
                   CASE b.entity_type
                       WHEN 'issue' THEN (i.id IS NULL OR i.deleted_at IS NOT NULL)
                       ELSE (pb.id IS NULL OR pb.deleted_at IS NOT NULL
                             OR pb.status = 'hidden')
                   END AS is_deleted_source
            FROM bookmarks b
            LEFT JOIN issues i
                   ON b.entity_type = 'issue' AND i.id = b.entity_id
            LEFT JOIN piri_boards pb
                   ON b.entity_type = 'board' AND pb.id = b.entity_id
            WHERE {where_sql}
            ORDER BY b.created_at DESC, b.id DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """,
            *params, limit, offset,
        )

    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": offset // limit + 1 if limit else 1,
        "page_size": limit,
        "pages": (total + limit - 1) // limit if limit and total else 0,
    }


async def get_status(
    pool: asyncpg.Pool, user_id: int, *, entity_type: str, entity_id: int
) -> dict:
    """สถานะของ entity เดียว — ให้ปุ่มไอคอนรู้ว่าจะวาดติ๊กหรือไม่"""
    _checked(entity_type)
    async with pool.acquire() as conn:
        bookmark_id = await conn.fetchval(
            """SELECT id FROM bookmarks
               WHERE user_id = $1 AND entity_type = $2 AND entity_id = $3""",
            user_id, entity_type, entity_id,
        )
    return {
        "bookmarked": bookmark_id is not None,
        "bookmark_id": bookmark_id,
    }


async def create_bookmark(
    pool: asyncpg.Pool, user_id: int, *, entity_type: str, entity_id: int
) -> Tuple[bool, dict]:
    """บันทึก — คืน `(created, bookmark)` โดย `created = False` แปลว่า "มีอยู่แล้ว"

    ⭐ **atomic upsert เดียว ไม่ใช่ "INSERT แล้วค่อย SELECT ถ้าชน"**
       ใช้ `ON CONFLICT DO UPDATE` + `(xmax = 0)` เพื่อรู้ว่าแถวนี้ *เพิ่ง insert* หรือ
       *มีอยู่ก่อน* ภายในคำสั่งเดียว — `xmax` ของ tuple ที่เพิ่ง insert เป็น 0
       ส่วน tuple ที่ถูก UPDATE จะมี `xmax` เป็น xid ของทรานแซกชันนั้น

       ถ้าใช้ `DO NOTHING` แล้วค่อย SELECT แทน จะมีช่วงว่างให้อีกทรานแซกชันลบแถวทิ้ง
       ระหว่างสองคำสั่ง ⇒ SELECT ได้ None แล้วไม่มีอะไรตอบกลับ (และถ้าเผลอคืน 201
       ทั้งที่ไม่มีแถว = โกหกผู้ใช้ว่าบันทึกแล้ว)
       ⇒ ประโยคเดียว = ไม่มีช่วงว่าง = ไม่ต้องมี retry loop

    ⚠️ entity ที่ไม่มีจริง/ถูกลบ → `NotFoundError` (404) — กัน bookmark ลอยที่ join ไม่เจออะไรเลย
       และตรวจ **ใน transaction เดียวกัน** กับการ insert ไม่งั้นมีช่องให้ entity ถูกลบ
       ระหว่างสองคำสั่งแล้วได้ bookmark ของสิ่งที่ถูกลบไปแล้ว
    """
    _checked(entity_type)
    async with pool.acquire() as conn:
        async with conn.transaction():
            exists = await conn.fetchval(_EXISTS_SQL[entity_type], entity_id)
            if exists is None:
                raise NotFoundError("ไม่พบเรื่อง/บอร์ดที่ต้องการบันทึก (อาจถูกลบไปแล้ว)")

            row = await conn.fetchrow(
                """
                INSERT INTO bookmarks (user_id, entity_type, entity_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, entity_type, entity_id) DO UPDATE
                    SET entity_type = EXCLUDED.entity_type
                RETURNING id, entity_type, entity_id, created_at, (xmax = 0) AS created
                """,
                user_id, entity_type, entity_id,
            )

    created = bool(row["created"])
    return created, {
        "id": row["id"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "created_at": row["created_at"],
    }


async def delete_bookmark(pool: asyncpg.Pool, user_id: int, bookmark_id: int) -> None:
    """เลิกบันทึก — **ลบจริง** ไม่ใช่ soft delete (ดู migration 021)

    ⚠️ **`AND user_id = $2` ห้ามลบออกเด็ดขาด** — นี่คือด่านเดียวที่กันการลบข้ามคน
       ถ้าลบเงื่อนไขนี้ ผู้ใช้คนไหนก็ลบ bookmark ของคนอื่นได้ถ้าเดา id ถูก
       (และจะไม่ error ด้วย — แถวของเจ้าของหายเงียบ ๆ) ⇒ มีเทสต์ B5 คุมอยู่
    """
    async with pool.acquire() as conn:
        deleted = await conn.fetchval(
            "DELETE FROM bookmarks WHERE id = $1 AND user_id = $2 RETURNING id",
            bookmark_id, user_id,
        )
    if deleted is None:
        raise NotFoundError("ไม่พบรายการที่บันทึกไว้")
