import asyncpg
from datetime import datetime, timedelta, timezone

from core.categories import (
    get_main_categories,
    get_main_category_description,
    get_subcategory_label,
)
from core.rbac import get_access_scope, require_permission_anywhere
from core.exceptions import ForbiddenError
# 🌟 ต้องรู้ "ปีปัจจุบัน" เพื่อไม่ให้นับคนซ้ำข้ามปี (migration 027)
from services import year_service

STATUS_LABELS = {
    "pending": "รอรับเรื่อง",
    "in_progress": "กำลังดำเนินการ",
    "resolved": "แก้ไขเสร็จ",
    "escalated": "ส่งต่อระดับบน",
    "cancelled": "ถูกยกเลิก",
    "rejected": "ถูกปัดตก",
}

# ลำดับสถานะคงที่ (ให้ UI เรียงแน่นอน + เติม 0 ให้ครบ)
STATUS_ORDER = ["pending", "in_progress", "escalated", "rejected", "resolved", "cancelled"]

# เขตเวลาโรงเรียน (ทุกที่ในระบบ)
BKK = timezone(timedelta(hours=7))

# ป้ายชื่อ action สำหรับกราฟสัดส่วนการใช้งาน (action → ภาษาไทย)
ACTION_LABELS = {
    "login": "เข้าสู่ระบบ",
    "CREATE_ISSUE": "แจ้งเรื่องใหม่",
    "UPDATE_ISSUE": "แก้ไขเรื่อง",
    "ACCEPT_ISSUE": "รับเรื่อง",
    "UPDATE_COUNTDOWN": "ตั้งเวลาแก้",
    "CREATE_STEP": "เพิ่มขั้นตอน",
    "UPDATE_STEP": "ทำขั้นตอนเสร็จ",
    "ESCALATE_ISSUE": "ส่งต่อระดับบน",
    "RESOLVE_ISSUE": "ปิดเรื่อง",
    "CANCEL_ISSUE": "ยกเลิกเรื่อง",
    "REJECT_ISSUE": "ปัดตกเรื่อง",
    "CREATE_COMMENT": "คอมเมนต์",
    "UPDATE_COMMENT": "แก้คอมเมนต์",
    "DELETE_COMMENT": "ลบคอมเมนต์",
    "CREATE_USER": "สร้างผู้ใช้",
    "CHANGE_PASSWORD": "เปลี่ยนรหัสผ่าน",
    "UPDATE_STUDENT": "แก้ไขนักเรียน",
    "CREATE_ROOM": "สร้างห้อง",
    "UPDATE_PROFILE": "แก้โปรไฟล์",
    "UPLOAD_IMPORT_EXCEL": "อัปโหลด Excel",
    "START_IMPORT_JOB": "เริ่มนำเข้า",
    "PROCESS_IMPORT_JOB": "กำลังนำเข้า",
    "COMPLETE_IMPORT_JOB": "นำเข้าสำเร็จ",
    "FAIL_IMPORT_JOB": "นำเข้าล้มเหลว",
    "RECOVER_IMPORT_JOB": "กู้คืนงานนำเข้า",
    "READ_ME": "ดูข้อมูลตัวเอง",
    "READ_PROFILE": "ดูโปรไฟล์",
    "READ_ISSUES": "ดูรายการเรื่อง",
    "READ_ISSUE": "ดูรายละเอียดเรื่อง",
    "READ_ROOMS": "ดูห้องเรียน",
    "READ_STUDENTS": "ดูรายชื่อนักเรียน",
    "READ_IMPORT_JOBS": "ดูงานนำเข้า",
    "READ_DASHBOARD": "ดูแดชบอร์ด",
    "READ_DASHBOARD_TRAFFIC": "ดูสถิติการใช้งาน",
    "READ_AUDIT_LOGS": "ดูบันทึกการใช้งาน",
    "CREATE_ANNOUNCEMENT": "สร้างประกาศ",
    "UPDATE_ANNOUNCEMENT": "แก้ไขประกาศ",
    "DELETE_ANNOUNCEMENT": "ลบประกาศ",
    "RESTORE_ANNOUNCEMENT": "กู้คืนประกาศ",
    "RETIRE_ANNOUNCEMENT": "ปลดระวางประกาศ",
    "UNRETIRE_ANNOUNCEMENT": "นำประกาศกลับมาใช้",
    "CREATE_ACADEMIC_TERM": "สร้างภาคเรียน",
    "UPDATE_ACADEMIC_TERM": "แก้ไขภาคเรียน",
    "DELETE_ACADEMIC_TERM": "ลบภาคเรียน",
    "RESTORE_ACADEMIC_TERM": "กู้คืนภาคเรียน",
    "SET_CURRENT_TERM": "ตั้งภาคปัจจุบัน",
    # E1 — ข้อเสนอจากผู้ใช้ (บอร์ดชนิด 'suggestion')
    "CREATE_SUGGESTION": "สร้างข้อเสนอแนะ",
    # A8 — ค่าตั้งระดับโรงเรียน (app_settings): ต้องมีป้ายที่นี่ **และ** ที่
    # frontend/src/views/audit/AuditLogs.vue (ACTION_LABELS) — กฎ "audit action ใหม่ = 2 ที่"
    "UPDATE_QUIET_HOURS": "ตั้งช่วงเวลาไม่ส่งแจ้งเตือน",
    # D1 — ระบบกิจกรรม (ตาราง events + event_registrations)
    # ⚠️ กฎ "audit action ใหม่ = 2 ที่" — ต้องมีป้ายที่นี่ **และ** ที่
    #    frontend/src/views/audit/AuditLogs.vue (ACTION_LABELS) เสมอ
    "CREATE_EVENT": "สร้างกิจกรรม",
    "UPDATE_EVENT": "แก้ไขกิจกรรม",
    "PUBLISH_EVENT": "เผยแพร่กิจกรรม",
    "CANCEL_EVENT": "ยกเลิกกิจกรรม",
    "DELETE_EVENT": "ลบกิจกรรม",
    "RESTORE_EVENT": "กู้คืนกิจกรรม",
    "REGISTER_EVENT": "ลงทะเบียนกิจกรรม",
    "UNREGISTER_EVENT": "ถอนการลงทะเบียนกิจกรรม",
}


def _action_label(action: str) -> str:
    """action string → ป้ายภาษาไทย (action ใหม่ที่ยังไม่มี label → แสดงค่าเดิม)"""
    if action in ACTION_LABELS:
        return ACTION_LABELS[action]
    return action


def _status_stats(counts: dict) -> list:
    """แปลง dict {status: count} → list ของทุกสถานะ เรียงตาม STATUS_ORDER (เติม 0 ถ้าไม่มี)"""
    return [
        {"status": st, "label": STATUS_LABELS.get(st, st), "count": int(counts.get(st, 0))}
        for st in STATUS_ORDER
    ]


def _scope_clause(scope: dict) -> tuple:
    """
    สร้าง WHERE clause + params จำกัดขอบเขตข้อมูลสำหรับ dashboard
    - scope='level' (ครูทั่วไป) → เฉพาะห้องที่ระดับชั้นตรงกับ staff_level (เช่น 'ม.4')
    - scope='super'/'all' (แอดมิน/ครูสภา/ประธานสภา) → ไม่จำกัด (ดูทั้งโรงเรียน)
    - scope อื่น (none = ครูไม่มีระดับ, pyramid = บทบาทที่ไม่มี scope กำหนด เช่น council_member)
      → ไม่เห็นข้อมูลใดเลย (fail-closed — กันเห็นทั้งโรงเรียนแบบเดียวกับ scope 'all')
    """
    if scope["scope"] == "level" and scope.get("level"):
        return " AND r.level = $1", [scope["level"]]
    if scope["scope"] in ("super", "all"):
        return "", []
    return " AND 1 = 0", []


async def get_dashboard(pool: asyncpg.Pool, user_id: int) -> dict:
    """
    สรุปสถิติ dashboard — กลุ่มตาม 3 หมวดหลัก (suggestion / wellbeing / report)
    - ตรวจสิทธิ์ VIEW_DASHBOARD ผ่าน core.rbac (super admin/is_admin ข้าม)
    - ครูทั่วไป (teacher): เห็นเฉพาะระดับชั้นตัวเอง (staff_level)
    """
    async with pool.acquire() as conn:
        # 1. สิทธิ์ดู dashboard (ข้ามทุกห้อง — teacher ก็มี VIEW_DASHBOARD)
        await require_permission_anywhere(conn, user_id, "VIEW_DASHBOARD")

        # 2. ขอบเขตข้อมูล: super / all / level / none
        scope = await get_access_scope(conn, user_id)
        level_where, level_params = _scope_clause(scope)

        # scope ที่ส่งให้ frontend: 'level' = เฉพาะระดับชั้น, 'none' = ไม่มีข้อมูล, 'all' = ทั้งโรงเรียน
        # ⚠️ fail-closed: scope ที่ไม่ได้ระบุไว้ (เช่น 'pyramid' ของบทบาทที่ยังไม่มี scope กำหนด)
        #    ต้องไม่ถูกเลื่อนเป็น 'all' — เดิม scope แปลกๆ รั่วไปเป็น 'all' → เห็นตัวเลขทั้งโรงเรียน
        # (สภานักเรียน council_member ได้ scope 'all' จาก get_access_scope แล้ว — เห็นทั้งโรงเรียนตามสิทธิ์)
        if scope["scope"] == "level":
            dashboard_scope = "level"
        elif scope["scope"] in ("super", "all"):
            dashboard_scope = "all"
        else:
            dashboard_scope = "none"

        # 3. หมวดหลักทั้ง 3 (จาก config/categories.json)
        main_categories = get_main_categories()
        category_codes = list(main_categories.keys())

        # ── 4. นับแยก (หมวดหลัก × สถานะ) — query เดียว ──
        rows = await conn.fetch(
            f"""
            SELECT i.main_category, i.status, COUNT(*) AS cnt
            FROM issues i
            LEFT JOIN rooms r ON r.id = i.room_id
            WHERE i.deleted_at IS NULL{level_where}
            GROUP BY i.main_category, i.status
            """,
            *level_params
        )
        by_main_status: dict = {}
        for r in rows:
            by_main_status.setdefault(r["main_category"], {})[r["status"]] = r["cnt"]

        # ── 5. หมวดย่อย × สถานะ (หมวดหลัก × หมวดย่อย × สถานะ) — query เดียว ──
        cat_status_rows = await conn.fetch(
            f"""
            SELECT i.main_category, i.category, i.status, COUNT(*) AS cnt
            FROM issues i
            LEFT JOIN rooms r ON r.id = i.room_id
            WHERE i.deleted_at IS NULL{level_where}
            GROUP BY i.main_category, i.category, i.status
            """,
            *level_params
        )
        by_cat_status: dict = {}
        for r in cat_status_rows:
            by_cat_status.setdefault(r["main_category"], []).append(r)

        # ── 6. เรื่องล่าสุดต่อหมวดหลัก (5 เรื่อง) — window function 1 query ──
        recent_rows = await conn.fetch(
            f"""
            SELECT * FROM (
                SELECT
                    i.id, i.main_category, i.category, i.title, i.status,
                    i.current_level, i.created_at, r.room_name,
                    ROW_NUMBER() OVER (
                        PARTITION BY i.main_category ORDER BY i.created_at DESC
                    ) AS rn
                FROM issues i
                LEFT JOIN rooms r ON r.id = i.room_id
                WHERE i.deleted_at IS NULL{level_where}
            ) sub
            WHERE sub.rn <= 5
            ORDER BY sub.main_category, sub.created_at DESC
            """,
            *level_params
        )
        recent_by_main: dict = {}
        for r in recent_rows:
            recent_by_main.setdefault(r["main_category"], []).append(r)

        # ── 7. รวมตัวเลขระดับบน (ทุกหมวด) ──
        # 💡 นับจากหมวดหลักที่รู้จักเท่านั้น — กันกรณี main_category อยู่นอก config (เช่นเก่าที่ถูกลบ)
        #    ทำให้ pending+in_progress+... == total_issues และ sum(main_categories[].total) == total_issues เสมอ
        total_by_main = {mc: sum(by_main_status.get(mc, {}).values()) for mc in category_codes}
        total_issues = sum(total_by_main.values())

        by_status_all: dict = {}
        for mc in category_codes:
            for st, cnt in by_main_status.get(mc, {}).items():
                by_status_all[st] = by_status_all.get(st, 0) + cnt
        by_status = _status_stats(by_status_all)

        # ── 8. งานเกินเวลา (รายหมวดหลัก) — กำลังดำเนินการ + countdown ล่าสุดเลยกำหนด ──
        # กลุ่มตาม main_category ให้ sum(overdue รายหมวด) == overdue รวมเสมอ
        overdue_rows = await conn.fetch(
            f"""
            SELECT i.main_category, COUNT(*) AS cnt
            FROM issues i
            LEFT JOIN rooms r ON r.id = i.room_id
            WHERE i.deleted_at IS NULL{level_where}
              AND i.status = 'in_progress'
              AND EXISTS (
                  SELECT 1 FROM issue_countdowns cd
                  WHERE cd.issue_id = i.id
                    AND cd.deadline < NOW()
                    AND cd.id = (
                        SELECT MAX(id) FROM issue_countdowns WHERE issue_id = i.id
                    )
              )
            GROUP BY i.main_category
            """,
            *level_params
        )
        overdue_by_main = {r["main_category"]: r["cnt"] for r in overdue_rows}
        overdue = sum(overdue_by_main.get(mc, 0) for mc in category_codes)

        # ── 9. จำนวนนักเรียน / ห้อง (ตาม scope) ──
        total_students, total_rooms = await _count_people(conn, scope)

        # ── 10. แนวโน้ม 7 วัน (เทียบวันตาม Asia/Bangkok) ──
        trend = await _trend_7days(conn, level_where, level_params, category_codes)

        # ── 11. การเข้าใช้งาน (audit_logs) — เฉพาะ scope 'super'/'all' (admin/ครูสภา/ประธานสภา/สภานักเรียน) ──
        # (ข้อมูลการเข้าระบบ = ข้อมูลข้ามระดับ — เฉพาะบทบาทระดับโรงเรียนที่เห็นทั้งโรงเรียน)
        if scope["scope"] in ("super", "all"):
            usage_count, recent_logins = await _usage(conn)
        else:
            usage_count, recent_logins = 0, []

        # ── 12. ประกอบผลลัพธ์ group ตาม 3 หมวดหลัก ──
        main_dashboards = []
        for code in category_codes:
            info = main_categories.get(code, {})
            sub_labels = info.get("subcategories", {})        # {code: label}
            sub_details = info.get("subcategory_details", {})  # {code: description}

            # รวมตัวเลขรายหมวดย่อยจาก (หมวดย่อย × สถานะ) — ใช้ config เป็นแกน
            # ให้ sum(subcategories[].count) == total เสมอ (บทเรียน: นับจาก key set เดียวกัน)
            # หมวดย่อยที่ไม่อยู่ใน config (หมวดเก่า/insert ตรง) → รวมเข้า "อื่นๆ" (ไม่ทิ้งข้อมูล)
            sub_counts: dict = {}
            sub_status: dict = {}
            other_count = 0
            other_status: dict = {}
            for r in by_cat_status.get(code, []):
                c = r["category"]
                if c in sub_labels:
                    sub_counts[c] = sub_counts.get(c, 0) + r["cnt"]
                    # ⚠️ อย่าห่อใส่ assignment เดียว: Python คำนวณ RHS ก่อน target
                    # (sub_status[c] จะ KeyError ถ้ายังไม่มี key) — แยกเป็น 2 บรรทัด
                    st = sub_status.setdefault(c, {})
                    st[r["status"]] = st.get(r["status"], 0) + r["cnt"]
                else:
                    other_count += r["cnt"]
                    other_status[r["status"]] = other_status.get(r["status"], 0) + r["cnt"]

            # รายการหมวดย่อย (เรียง count มากไปน้อย — อันเยอะสุดอยู่บน; เสมอ → เรียงตาม config)
            sub_items = [
                {"category": c, "label": sub_labels[c],
                 "description": sub_details.get(c, ""),
                 "count": sub_counts.get(c, 0), "by_status": sub_status.get(c, {})}
                for c in sub_labels
            ]
            sub_items.sort(key=lambda x: x["count"], reverse=True)
            # "อื่นๆ" ต่อท้ายเสมอ (ไม่ไปแทรกกลาง leaderboard — เป็นหมวดตกค้าง ไม่ใช่หมวดจริง)
            if other_count > 0:
                sub_items.append({
                    "category": "_other", "label": "อื่นๆ",
                    "description": "หมวดย่อยที่ไม่อยู่ในระบบปัจจุบัน",
                    "count": other_count, "by_status": other_status,
                })
            subcategories = [
                {
                    "category": it["category"], "label": it["label"],
                    "description": it["description"], "count": it["count"],
                    "by_status": _status_stats(it["by_status"]),
                }
                for it in sub_items
            ]

            # เรื่องล่าสุดในหมวด (สำหรับคลิกเข้าไปติดตาม)
            recent_issues = [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "main_category": code,
                    "category": r["category"],
                    "category_label": get_subcategory_label(code, r["category"]),
                    "status": r["status"],
                    "current_level": r["current_level"],
                    "room_name": r["room_name"],
                    "created_at": r["created_at"],
                }
                for r in recent_by_main.get(code, [])
            ]

            main_dashboards.append({
                "code": code,
                "label": info.get("label", code),
                "description": get_main_category_description(code),
                "total": total_by_main.get(code, 0),
                "overdue": overdue_by_main.get(code, 0),
                "by_status": _status_stats(by_main_status.get(code, {})),
                "subcategories": subcategories,
                "recent_issues": recent_issues,
            })

    return {
        "scope": dashboard_scope,
        "scope_label": scope.get("level") if dashboard_scope == "level" else None,
        "total_issues": total_issues,
        "pending": by_status_all.get("pending", 0),
        "in_progress": by_status_all.get("in_progress", 0),
        "resolved": by_status_all.get("resolved", 0),
        "escalated": by_status_all.get("escalated", 0),
        "cancelled": by_status_all.get("cancelled", 0),
        "rejected": by_status_all.get("rejected", 0),
        "overdue": overdue,
        "total_students": total_students,
        "total_rooms": total_rooms,
        "by_status": by_status,
        "main_categories": main_dashboards,
        "trend": trend,
        "usage_count": usage_count,
        "recent_logins": recent_logins,
    }


async def get_dashboard_traffic(pool: asyncpg.Pool, user_id: int) -> dict:
    """
    สถิติการเข้าใช้งานละเอียด (30 วัน) จาก audit_logs:
    daily_logins / daily_actions / daily_active_users / action_breakdown + สรุปสะสม
    - เฉพาะ scope 'super'/'all' (admin/ครูสภา/ประธานสภา/สภานักเรียน) — ครู (level/none) → 403
    - กลุ่มวันตาม Asia/Bangkok (แบบ _trend_7days) + เติมวันที่ไม่มีข้อมูลด้วย 0
    """
    async with pool.acquire() as conn:
        await require_permission_anywhere(conn, user_id, "VIEW_DASHBOARD")
        scope = await get_access_scope(conn, user_id)
        if scope["scope"] not in ("super", "all"):
            raise ForbiddenError("คุณไม่มีสิทธิ์ดูข้อมูลการใช้งานของระบบ")

        today = datetime.now(timezone.utc).astimezone(BKK).date()
        start = today - timedelta(days=29)

        # ── 1. เข้าสู่ระบบสำเร็จต่อวัน ──
        login_rows = await conn.fetch(
            """
            SELECT (created_at AT TIME ZONE 'Asia/Bangkok')::date AS day, COUNT(*) AS cnt
            FROM audit_logs
            WHERE action = 'login' AND status = 'success'
              AND (created_at AT TIME ZONE 'Asia/Bangkok')::date >= $1
            GROUP BY day
            """,
            start
        )
        # ── 2. กิจกรรมทั้งหมดต่อวัน (ทุก action) ──
        action_rows = await conn.fetch(
            """
            SELECT (created_at AT TIME ZONE 'Asia/Bangkok')::date AS day, COUNT(*) AS cnt
            FROM audit_logs
            WHERE (created_at AT TIME ZONE 'Asia/Bangkok')::date >= $1
            GROUP BY day
            """,
            start
        )
        # ── 3. ผู้ใช้ที่ใช้งานต่อวัน (distinct user_id) ──
        active_rows = await conn.fetch(
            """
            SELECT (created_at AT TIME ZONE 'Asia/Bangkok')::date AS day, COUNT(DISTINCT user_id) AS cnt
            FROM audit_logs
            WHERE user_id IS NOT NULL
              AND (created_at AT TIME ZONE 'Asia/Bangkok')::date >= $1
            GROUP BY day
            """,
            start
        )
        # ── 4. สรุปสะสม + สัดส่วนราย action (top 10) ──
        total_logins = await conn.fetchval(
            "SELECT COUNT(*) FROM audit_logs WHERE action = 'login' AND status = 'success'"
        ) or 0
        failed_logins = await conn.fetchval(
            "SELECT COUNT(*) FROM audit_logs WHERE action = 'login' AND status = 'error'"
        ) or 0
        unique_users = await conn.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM audit_logs WHERE user_id IS NOT NULL"
        ) or 0
        breakdown_rows = await conn.fetch(
            """
            SELECT action, COUNT(*) AS cnt
            FROM audit_logs
            GROUP BY action
            ORDER BY cnt DESC
            LIMIT 10
            """
        )

        def _fill_days(rows: list) -> list:
            """เติม 30 วันที่ต่อเนื่อง (ใหม่→เก่า) วันที่ไม่มีข้อมูล = 0"""
            counts = {r["day"]: r["cnt"] for r in rows}
            out = []
            for i in range(29, -1, -1):
                day = today - timedelta(days=i)
                out.append({"date": day.isoformat(), "count": counts.get(day, 0)})
            return out

        return {
            "daily_logins": _fill_days(login_rows),
            "daily_actions": _fill_days(action_rows),
            "daily_active_users": _fill_days(active_rows),
            "action_breakdown": [
                {"action": r["action"], "label": _action_label(r["action"]), "count": r["cnt"]}
                for r in breakdown_rows
            ],
            "total_logins": total_logins,
            "unique_users": unique_users,
            "failed_logins": failed_logins,
        }


async def _count_people(conn: asyncpg.Connection, scope: dict) -> tuple:
    """
    จำนวนนักเรียน/ห้อง
    - scope='level' (ครูทั่วไป) → นับเฉพาะระดับชั้นตัวเอง
    - scope='super'/'all' (แอดมิน/ครูสภา/ประธานสภา) → นับทั้งโรงเรียน
    - scope อื่น (none/pyramid) → 0 (fail-closed — ไม่เห็นจำนวนทั้งโรงเรียน)

    🌟 **นับเฉพาะปีปัจจุบัน** (migration 027) — ก่อนมีปี ตาราง `students` มีคนละ 1 แถว
       ⇒ `COUNT(*)` = จำนวนคน · หลังมีปี คนหนึ่งมีได้หลายแถว (ปีเก่า + ปีใหม่)
       ⇒ ถ้าไม่กรอง **ยอดจะบวมขึ้นทุกปี** โดยที่ตัวเลขยังดูสมเหตุสมผล (ไม่มีทางรู้ว่าผิด)
       ⚠️ ตัวกรองระดับชั้น (`r.level`) ไม่มีผลกับคนที่ `room_id IS NULL` อยู่แล้ว (LEFT JOIN
          + เงื่อนไขบน r) ⇒ ไม่ต้องแก้ตรรกะนั้น
    """
    current_year = await year_service.fetch_current_year(conn)
    year_id = current_year["id"] if current_year else None

    if scope["scope"] == "level" and scope.get("level"):
        level = scope["level"]
        total_students = await conn.fetchval(
            """
            SELECT COUNT(*) FROM students s
            LEFT JOIN rooms r ON r.id = s.room_id
            WHERE s.deleted_at IS NULL AND r.level = $1
              AND s.academic_year_id = $2
            """,
            level, year_id
        ) or 0
        total_rooms = await conn.fetchval(
            "SELECT COUNT(*) FROM rooms r WHERE r.deleted_at IS NULL AND r.level = $1",
            level
        ) or 0
    elif scope["scope"] in ("super", "all"):
        total_students = await conn.fetchval(
            "SELECT COUNT(*) FROM students WHERE deleted_at IS NULL AND academic_year_id = $1",
            year_id
        ) or 0
        total_rooms = await conn.fetchval(
            "SELECT COUNT(*) FROM rooms WHERE deleted_at IS NULL"
        ) or 0
    else:
        # ครูที่ยังไม่มี staff_level / บทบาทที่ไม่มี scope กำหนด → ไม่เห็นจำนวนนักเรียน/ห้องเลย
        return 0, 0
    return total_students, total_rooms


async def _trend_7days(conn: asyncpg.Connection, level_where: str, level_params: list, category_codes: list) -> list:
    """แนวโน้ม 7 วันย้อนหลัง (นับวันตาม Asia/Bangkok) — 1 query แล้วเติมวันที่ที่ไม่มีเรื่อง"""
    today = datetime.now(timezone.utc).astimezone(BKK).date()

    # ⚠️ ต้องกรอง main_category ด้วย key set เดียวกับ total_issues/by_status/overdue (category_codes)
    #    — ถ้าไม่กรอง หมวดที่อยู่นอก config (เก่า/insert ตรง) จะขึ้นในกราฟแต่ไม่อยู่ในตัวเลขอื่น
    #    (บทเรียน: "Dashboard หลาย query รวมหมวดเดียว" — ตัวเลขทุกจุดต้องนับจาก key set เดียวกัน)
    # ระบุ placeholder ให้ต่อจาก level_params (บทเรียน: นับ $n ให้ครบ — อย่าเริ่ม $1 ซ้ำ)
    next_param = len(level_params) + 1
    cat_param = next_param        # $n      = หมวดหลักที่รู้จัก
    date_param = next_param + 1   # $n+1    = วันที่เริ่มต้น
    rows = await conn.fetch(
        f"""
        SELECT (i.created_at AT TIME ZONE 'Asia/Bangkok')::date AS day, COUNT(*) AS cnt
        FROM issues i
        LEFT JOIN rooms r ON r.id = i.room_id
        WHERE i.deleted_at IS NULL{level_where}
          AND i.main_category = ANY(${cat_param}::text[])
          AND (i.created_at AT TIME ZONE 'Asia/Bangkok')::date >= ${date_param}
        GROUP BY day
        """,
        *level_params, category_codes, today - timedelta(days=6)
    )
    counts = {r["day"]: r["cnt"] for r in rows}

    trend = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        trend.append({"date": day.isoformat(), "count": counts.get(day, 0)})
    return trend


async def _usage(conn: asyncpg.Connection) -> tuple:
    """จำนวนการเข้าใช้งาน + ผู้เข้าใช้ล่าสุด (จาก audit_logs — ถ้ายังไม่มีข้อมูลให้เป็น 0)
    ⚠️ นับเฉพาะ login ที่สำเร็จ (status='success') — failed login ถูกบันทึกเป็น action='login' status='error' แล้ว"""
    usage_count = 0
    recent_logins = []
    try:
        usage_count = await conn.fetchval(
            "SELECT COUNT(*) FROM audit_logs WHERE action = 'login' AND status = 'success'"
        ) or 0
        login_rows = await conn.fetch(
            """
            SELECT actor_identifier, created_at FROM audit_logs
            WHERE action = 'login' AND status = 'success'
            ORDER BY created_at DESC LIMIT 10
            """
        )
        recent_logins = [
            {"actor": r["actor_identifier"], "at": r["created_at"]}
            for r in login_rows
        ]
    except Exception:
        pass  # audit_logs อาจยังไม่มีข้อมูล
    return usage_count, recent_logins
