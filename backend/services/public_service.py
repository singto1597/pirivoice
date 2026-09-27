"""Public API — ข้อมูลสาธารณะสำหรับ Landing Page (ไม่ต้องล็อกอิน)

โฟกัสที่ความปลอดภัยของข้อมูล: เปิดเผยเฉพาะภาพรวม / เรื่องที่ปิดแล้วแบบ mask ตัวตน
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg

# ── แมป priority → impact_score (ระดับผลกระทบ 1–10) ──
_PRIORITY_IMPACT = {"low": 3, "normal": 5, "high": 7, "urgent": 9}

# ── แมปบทบาทผู้รับงาน → "ตำแหน่ง/หน่วยงานที่รับผิดชอบ" (ภาษาไทย) ──
_ROLE_DEPARTMENT = {
    "student": "นักเรียน",
    "class_president": "หัวหน้าห้อง",
    "vice_academic": "รองวิชาการ",
    "vice_discipline": "รองวินัย",
    "vice_activity": "รองกิจกรรม",
    "vice_reception": "รองปฏิคม",
    "level_president": "ประธานระดับ",
    "level_vice_president": "ผู้ช่วยหัวหน้าระดับ",
    "council_member": "สภานักเรียน",
    "council_president": "ประธานสภา",
    "teacher_council": "ครูสภา",
    "teacher": "ครู",
    "admin": "ฝ่ายบริหาร",
}


def _mask_reporter(is_anonymous: bool, level: Optional[str], room_no: Optional[int]) -> str:
    """Mask ตัวตนผู้แจ้ง — เช่น 'นักเรียน ม.4/1' หรือ 'นักเรียน (ไม่ประสงค์ออกนาม)'"""
    if is_anonymous:
        return "นักเรียน (ไม่ประสงค์ออกนาม)"
    level_txt = (level or "").strip()
    if level_txt:
        base = f"นักเรียน {level_txt}"
        if room_no:
            base = f"{base}/{room_no}"
        return base
    return "นักเรียน"


def _role_department(role: Optional[str]) -> str:
    return _ROLE_DEPARTMENT.get(role or "") or "สภานักเรียน"


def _duration_hours(resolved_at, created_at) -> Optional[float]:
    if not resolved_at or not created_at:
        return None
    hours = (resolved_at - created_at).total_seconds() / 3600.0
    return round(hours, 1)


async def get_system_stats(pool: asyncpg.Pool) -> dict:
    """สถิติรวมของระบบ (Public)

    เน้นเมตริก "ความ Active" ของระบบมากกว่าจุดจบคดี (ตาม UX feedback):
    - total_issues: เรื่องที่เข้าสู่ระบบแล้ว
    - resolved_issues: เรื่องที่ปิดสำเร็จแล้ว (จำนวนจริง ไม่ใช่ %)
    - routed_issues: เรื่องที่กำลังดำเนินการ/ส่งต่อฝ่ายที่เกี่ยวข้องแล้ว
    """
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM issues WHERE deleted_at IS NULL"
        ) or 0
        resolved = await conn.fetchval(
            "SELECT COUNT(*) FROM issues WHERE deleted_at IS NULL AND status = 'resolved'"
        ) or 0
        routed = await conn.fetchval(
            """
            SELECT COUNT(*) FROM issues
            WHERE deleted_at IS NULL AND status IN ('in_progress', 'escalated')
            """
        ) or 0
        resolved_rate = round((resolved / total * 100), 1) if total else 0.0
        avg_hours = await conn.fetchval(
            """
            SELECT COALESCE(AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600.0), 0)
            FROM issues
            WHERE deleted_at IS NULL
              AND status = 'resolved'
              AND resolved_at IS NOT NULL
              AND created_at IS NOT NULL
            """
        )
        talk_threads = await conn.fetchval(
            """
            SELECT COUNT(*) FROM piri_boards
            WHERE deleted_at IS NULL AND status = 'active' AND board_type = 'talk'
            """
        ) or 0
        votes = await conn.fetchval(
            "SELECT COUNT(*) FROM piri_votes WHERE deleted_at IS NULL"
        ) or 0

    return {
        "total_issues": total,
        "resolved_issues": resolved,
        "routed_issues": routed,
        "resolved_rate_percent": float(resolved_rate),
        "avg_resolve_hours": round(float(avg_hours or 0), 1),
        "active_talk_threads": talk_threads,
        "active_votes": votes,
    }


async def get_stats_trend(pool: asyncpg.Pool, days: int) -> list[dict]:
    """แนวโน้มจำนวนเรื่องใหม่ต่อวัน ย้อนหลัง N วัน (Public) — ข้อมูลจริงสำหรับ Sparkline

    นับตามวันที่ (Asia/Bangkok) ของ created_at แล้วเติมวันว่างเป็น 0
    เพื่อให้กราฟเห็นภาพ "ระบบเริ่มขยับ" แม้บางวันไม่มีเรื่อง
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT (created_at AT TIME ZONE 'Asia/Bangkok')::date AS day, COUNT(*)::int AS count
            FROM issues
            WHERE deleted_at IS NULL
              AND created_at >= NOW() - ($1::int * INTERVAL '1 day')
            GROUP BY day
            ORDER BY day
            """,
            days,
        )

    counts = {r["day"].isoformat(): r["count"] for r in rows}
    # วันที่ "วันนี้" ในเวลาไทย (UTC+7) — เริ่มนับจากวันวานถอยหลังให้ครบ `days` วัน
    now_bkk = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=7)))
    today = now_bkk.date()
    out: list[dict] = []
    for offset in range(days - 1, -1, -1):
        d = today - timedelta(days=offset)
        iso = d.isoformat()
        out.append({"date": iso, "count": counts.get(iso, 0)})
    return out


async def get_resolved_cases(pool: asyncpg.Pool, limit: int) -> list[dict]:
    """เรื่องที่ปิดงานแล้วล่าสุด (Public) — เปิดเผยเฉพาะ summary + สรุปวิธีแก้"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                i.id,
                i.title,
                i.category,
                i.priority,
                i.is_anonymous,
                i.reporter_name,
                i.resolved_at,
                i.created_at,
                i.current_assignee_role,
                r.level       AS reporter_level,
                r.room_number AS reporter_room_no
            FROM issues i
            LEFT JOIN rooms r ON r.id = i.reporter_room_id
            WHERE i.deleted_at IS NULL
              AND i.status = 'resolved'
              AND i.resolved_at IS NOT NULL
            ORDER BY i.resolved_at DESC
            LIMIT $1
            """,
            limit,
        )

        out: list[dict] = []
        for row in rows:
            # สรุปวิธีแก้: note ล่าสุดตอนสถานะเปลี่ยนเป็น resolved
            summary = await conn.fetchval(
                """
                SELECT note FROM issue_status_history
                WHERE issue_id = $1 AND status = 'resolved'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                row["id"],
            )
            out.append(
                {
                    "id": str(row["id"]),
                    "title": row["title"],
                    "category": row["category"],
                    "reporter_mask": _mask_reporter(
                        row["is_anonymous"], row["reporter_level"], row["reporter_room_no"]
                    ),
                    "resolved_at": row["resolved_at"],
                    "solution_summary": (summary or "เรื่องนี้ถูกปิดเรียบร้อยแล้ว").strip(),
                    "department_in_charge": _role_department(row["current_assignee_role"]),
                    "impact_score": _PRIORITY_IMPACT.get(row["priority"], 5),
                    "duration_hours": _duration_hours(row["resolved_at"], row["created_at"]),
                }
            )
        return out


async def get_announcements(pool: asyncpg.Pool) -> list[dict]:
    """
    ประกาศสาธารณะ — เรียง urgent/high มาก่อน

    ⚠️ **กรองเองโดยไม่ผ่าน `_STATUS_CONDITIONS`** (dict นั้นอยู่ใน announcement_service
       ซึ่งเป็นฝั่ง admin) ⇒ ถ้าเพิ่ม/แก้สถานะใหม่ ต้องมาเติมเงื่อนไขที่นี่ด้วยเสมอ
       ไม่งั้นประกาศที่ปลดระวางจะยังโชว์บน Landing Page ทั้งที่เทสต์อื่นเขียวหมด

    ⚠️ endpoint นี้ถูกเรียกโดย **2 หน้า**: `Landing.vue` (ไม่ล็อกอิน — hero pill + marquee)
       และ `Home.vue` (ใน /app) ⇒ แก้ที่นี่ที่เดียวมีผลทั้งคู่

    ⭐ จงใจ **ไม่ใส่ LIMIT** ตามที่เจ้าของระบบสั่ง ("ให้โชว์ทั้งหมดที่ยังไม่ถอดออก")
       ซึ่งขัดกับ docs/rules/backend.md ข้อ 3 (list ยาวต้องมี pagination)
       ⇒ ยอมรับได้เพราะตารางนี้มีหลักหน่วยถึงหลักสิบแถว ; ถ้าวันหนึ่งโตถึงหลักพัน
         ต้องกลับมาคุยเรื่อง pagination หรือ LIMIT เพดาน
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, message, priority, link
            FROM announcements
            WHERE deleted_at IS NULL AND retired_at IS NULL
            ORDER BY
                (CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END),
                created_at DESC
            """
        )
        return [dict(r) for r in rows]
