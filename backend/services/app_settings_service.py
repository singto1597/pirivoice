"""🔇 Quiet Hours (A8) — ช่วงเวลาที่ **โรงเรียนไม่ส่ง push** (ค่าตั้งระดับโรงเรียน)

**ทำไมต้องมี:** ก่อนหน้านี้ `push_outbox` ยิงทุกแจ้งเตือนออกทันทีไม่ว่าเวลากี่โมง
⇒ ตอนสอบ / ตอนกลางคืน / ตอนประชุมทั้งโรงเรียน มือถือทั้งโรงเรียนดังพร้อมกัน
และ **การปิดรายกลุ่ม (A2) ช่วยไม่ได้** เพราะมันคือ "ปิดของฉันคนเดียว" ไม่ใช่ "โรงเรียนขอความสงบ"
⇒ ต้องมีค่าตั้ง **ระดับโรงเรียน** ที่สภาแก้เองได้โดยไม่ต้อง deploy

⭐ **ที่เก็บคือ `app_settings` (key/value jsonb — migration 023) ไม่ใช่คอลัมน์ใหม่บน
   `notification_preferences`** — ตารางนั้นเป็น "ความต้องการของแต่ละคน" ส่วนนี่เป็น "คำสั่งของโรงเรียน"
   คนละเจ้าของ คนละอายุการใช้งาน ⇒ รวมกันเมื่อไรจะตอบไม่ได้ว่าแถวหนึ่งเป็นของใคร

⭐ **"ไม่มีแถว" = ไม่ปิดกั้นอะไร** — หลักเดียวกับ A2 (`notification_preferences`) และตามที่
   migration 023 เขียนกำกับไว้ · `DEFAULT_*` ด้านล่าง **เป็นเพียงค่าที่ UI เริ่มต้นให้เห็น**
   ไม่ใช่ค่าที่ถูกบังคับใช้ ⇒ โรงเรียนที่ไม่เคยแตะการ์ดนี้จะไม่มีการปิด push เลยแม้แต่วินาทีเดียว

⚠️ **ด่านนี้อยู่ที่ push worker เท่านั้น — in-app ไม่ถูกปิดกั้น** (ดู `push_service.process_pending`)
   แถวใน `notifications` ยังถูกสร้างครบเหมือนเดิม ⇒ **ไม่มีอะไรหายไป แค่ไม่มีเสียง**
   ⇒ เป็นเหตุผลที่ `PUSH` ต้องแยกจาก `enabled` ของ A2 ไม่ใช่ไปแก้ของเดิม
   (ตามข้อผูกพันใน `migrations/016_notification_preferences.py` L15-17)

⚠️ **เขตเวลาตายตัวที่ `Asia/Bangkok` (UTC+7)** — ตามธรรมเนียมโปรเจค (`dashboard_service.BKK`)
   ไทยไม่มี DST ⇒ `timezone(timedelta(hours=7))` เทียบเท่า `ZoneInfo` แต่ตรงกับที่อื่นในโค้ด
   ⚠️ **ห้ามใช้เวลาของเซิร์ฟเวอร์ตรง ๆ** — production รันเป็น UTC ⇒ "22:00" จะหมายถึงตี 5 ไทย

⚠️ **ทุกฟังก์ชันอ่านในไฟล์นี้ "ไม่เชื่อข้อมูลใน DB"** — เจอค่าที่ parse ไม่ได้ = ปิดไว้ก่อน
   เพราะทางเลือกอีกทางคือเดา แล้วเผลอปิด push ทั้งโรงเรียนด้วยข้อมูลที่เสีย
"""
import json
import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import asyncpg

from core.exceptions import ValidationError
from core.logger import AuditLogger
from core.rbac import require_permission_anywhere

logger = logging.getLogger("APP_SETTINGS")

# กุญแจใน `app_settings` — มีตัวเดียวตอนนี้ (ตัวถัดไปตามแผน: `push_muted_types`)
QUIET_HOURS_KEY = "quiet_hours"

# สิทธิ์เดียวกับงานตั้งค่าอื่นของโรงเรียน (ภาคเรียน) — มีอยู่แล้วใน roles.json
# ⇒ **ไม่ต้องมี migration backfill permission**
PERMISSION = "MANAGE_SETTINGS"

# เขตเวลาโรงเรียน (ทุกที่ในระบบ) — เหมือน `dashboard_service.BKK` เป๊ะ
BKK = timezone(timedelta(hours=7))

# ค่าที่ **UI เริ่มต้นแสดง** เมื่อโรงเรียนยังไม่เคยตั้ง (ไม่ใช่ค่าที่ถูกบังคับใช้)
DEFAULT_START = "22:00"
DEFAULT_END = "06:00"

_MINUTES_PER_DAY = 24 * 60


# ============================================================
# 🧮 ฟังก์ชันบริสุทธิ์ (ไม่มี DB) — "หน้าตา" และ "ความหมาย" ของค่าตั้ง
#    แยกออกมาเพราะเป็นตรรกะที่ต้องเทสต์ตรง ๆ ได้ (และ worker เรียกทุก batch)
# ============================================================

def _parse_hhmm(raw: Any) -> Optional[int]:
    """`"22:00"` → 1320 (นาทีนับจากเที่ยงคืน) · ค่าที่ไม่ใช่รูปนี้ → `None`"""
    if not isinstance(raw, str):
        return None
    parts = raw.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hours, minutes = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return None
    return hours * 60 + minutes


def _fmt_hhmm(total: int) -> str:
    """1320 → `"22:00"` (ทิศทางกลับของ `_parse_hhmm`)"""
    return f"{total // 60:02d}:{total % 60:02d}"


def _as_dict(raw: Any) -> Optional[Dict[str, Any]]:
    """jsonb ที่ asyncpg คืนมาเป็น **string** → dict (บทเรียนเดิมใน skills.md)

    รับ dict ผ่านตรง ๆ ด้วย เพื่อให้เทสต์เรียกได้โดยไม่ต้องผ่าน DB
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def normalize_quiet_hours(value: Any) -> Dict[str, Any]:
    """ค่าดิบจาก DB → รูปมาตรฐาน `{"enabled", "start", "end"}` — **ไม่มีทางโยน**

    ใช้ทั้งตอนอ่านจาก DB และตอนคืนค่าเริ่มต้น ⇒ **ที่เดียวที่นิยาม "ค่าตั้งนี้แปลว่าอะไร"**
    · ไม่มีค่า / รูปผิด / เวลาที่ parse ไม่ได้ ⇒ ปิดไว้ + คืนค่าเริ่มต้น (พร้อม log เตือน)
    · `start == end` ⇒ ปิด (ช่วงเวลาที่เริ่มและจบเวลาเดียวกัน = ไม่มีช่วงเวลา)
    """
    data = _as_dict(value)
    if data is None:
        return {"enabled": False, "start": DEFAULT_START, "end": DEFAULT_END}

    start_min = _parse_hhmm(data.get("start"))
    end_min = _parse_hhmm(data.get("end"))
    if start_min is None or end_min is None:
        logger.warning(
            "⚠️ ค่า quiet_hours ใน app_settings อ่านไม่ได้ (%r) — ถือว่าปิด "
            "(ไม่เดา เพราะเดาผิด = ปิด push ทั้งโรงเรียน)",
            data,
        )
        return {"enabled": False, "start": DEFAULT_START, "end": DEFAULT_END}

    return {
        "enabled": bool(data.get("enabled")) and start_min != end_min,
        "start": _fmt_hhmm(start_min),
        "end": _fmt_hhmm(end_min),
    }


def quiet_hours_window(config: Optional[Dict[str, Any]]) -> Optional[Tuple[int, int]]:
    """ช่วงเวลาที่จะปิด เป็น `(start_min, end_min)` หรือ `None` ถ้าไม่มีช่วงที่ใช้ได้

    **ที่เดียวที่ตัดสินว่า "ค่าตั้งนี้มีผลไหม"** — `quiet_hours_active` และ `quiet_hours_resumes_at`
    เรียกตัวนี้ทั้งคู่ ⇒ สองฟังก์ชันไม่มีทางเข้าใจค่าตั้งไม่ตรงกัน
    """
    if not config or not config.get("enabled"):
        return None
    start_min = _parse_hhmm(config.get("start"))
    end_min = _parse_hhmm(config.get("end"))
    if start_min is None or end_min is None or start_min == end_min:
        return None
    return start_min, end_min


def _now_bkk(now: Optional[datetime] = None) -> datetime:
    """เวลาปัจจุบันในเขตโรงเรียน — `now` แบบ naive ถือเป็น UTC (ไม่ปล่อยให้ตีความตาม locale)"""
    if now is None:
        return datetime.now(timezone.utc).astimezone(BKK)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(BKK)


def quiet_hours_active(config: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> bool:
    """**ตอนนี้** อยู่ในช่วงปิด push หรือไม่ — ฟังก์ชันบริสุทธิ์ (worker ใช้ตัวนี้)

    รองรับช่วงที่ **ข้ามเที่ยงคืน** (`22:00–06:00` = ช่วงปกติของงานนี้)
    """
    window = quiet_hours_window(config)
    if window is None:
        return False
    start_min, end_min = window
    local = _now_bkk(now)
    minutes = local.hour * 60 + local.minute

    if start_min < end_min:
        return start_min <= minutes < end_min
    # ข้ามเที่ยงคืน: 22:00–06:00 ⇒ ตั้งแต่ 22:00 ถึงเที่ยงคืน **หรือ** ก่อน 06:00
    return minutes >= start_min or minutes < end_min


def quiet_hours_resumes_at(
    config: Optional[Dict[str, Any]], now: Optional[datetime] = None
) -> Optional[datetime]:
    """เวลาที่จะ **กลับมาส่ง push** (เขตไทย) หรือ `None` ถ้าไม่ได้ปิดอยู่

    มีไว้เพื่อให้ log ของ worker บอกได้ว่า "ปิดถึงกี่โมง" — ไม่มีตัวเลขนี้ ผู้ดูแลจะรู้แค่ว่า
    "push ไม่ส่ง" ซึ่งแยกไม่ออกระหว่าง quiet hours กับระบบพัง
    """
    window = quiet_hours_window(config)
    if window is None:
        return None
    _start_min, end_min = window
    local = _now_bkk(now)

    resume = datetime.combine(local.date(), time(end_min // 60, end_min % 60), tzinfo=BKK)
    if resume <= local:
        resume += timedelta(days=1)
    return resume


# ============================================================
# 📖 อ่าน
# ============================================================

async def fetch_quiet_hours(conn: asyncpg.Connection) -> Dict[str, Any]:
    """อ่านค่าตั้งโดยใช้ connection ของ caller (ให้ reuse ได้ในคิวรีชุดเดียว)

    คืน `updated_at` มาด้วย — `None` = โรงเรียนยังไม่เคยตั้ง (UI ใช้แยก "ค่าเริ่มต้น" จาก "ที่ตั้งไว้")
    """
    row = await conn.fetchrow(
        "SELECT value, updated_at FROM app_settings WHERE key = $1", QUIET_HOURS_KEY
    )
    if not row:
        return {**normalize_quiet_hours(None), "updated_at": None}
    return {**normalize_quiet_hours(row["value"]), "updated_at": row["updated_at"]}


async def get_quiet_hours(pool: asyncpg.Pool) -> Dict[str, Any]:
    """ค่าตั้ง quiet hours ปัจจุบัน — **ไม่มี permission check** (ใครก็อ่านได้)

    ⭐ ต่างจาก endpoint อื่นใน `settings_router` โดยเจตนา: ค่านี้มีไว้ **อธิบายให้นักเรียนทุกคน
       เข้าใจว่าทำไมมือถือเงียบ** ⇒ ถ้าปิดการอ่าน เท่ากับซ่อนคำอธิบายจากคนที่ได้รับผลกระทบ
       และมันไม่ได้มีข้อมูลอ่อนไหวใด ๆ (แค่ช่วงเวลา) ⇒ GET เปิด · PUT ต้อง `MANAGE_SETTINGS`
    """
    async with pool.acquire() as conn:
        return await fetch_quiet_hours(conn)


# ============================================================
# ✍️ เขียน
# ============================================================

async def set_quiet_hours(
    pool: asyncpg.Pool,
    user_id: int,
    *,
    enabled: bool,
    start: str,
    end: str,
) -> Dict[str, Any]:
    """ตั้งค่า quiet hours + audit (upsert — แถวเกิดครั้งแรกที่นี่)

    ⚠️ **`enabled=True` พร้อม `start == end` ถูกปฏิเสธด้วย 400 ไม่ใช่ปรับให้เป็น `false` เงียบ ๆ**
       แผนแรกเขียนว่าให้ "บังคับปิด" — เปลี่ยนเป็นปฏิเสธเพราะการปิดสวิตช์ที่ผู้ใช้เพิ่งเปิด
       โดยไม่บอกอะไรเลย คือความล้มเหลวแบบเงียบ ที่ผู้ใช้จะเห็นเป็น "กดเปิดแล้วมันเด้งกลับ"
       โดยไม่รู้ว่าทำไม · 400 พร้อมข้อความไทยบอกสาเหตุตรง ๆ ดีกว่า
       (และยังคงเจตนาเดิม: **ไม่มีทางที่ DB จะเก็บสภาพ `enabled=true` + `22:00–22:00`**)
    """
    start = (start or "").strip()
    end = (end or "").strip()

    if _parse_hhmm(start) is None or _parse_hhmm(end) is None:
        raise ValidationError("รูปแบบเวลาต้องเป็น HH:MM (เช่น 22:00)")
    if enabled and start == end:
        raise ValidationError("เวลาเริ่มกับเวลาสิ้นสุดต้องไม่เท่ากัน — ถ้าไม่ต้องการปิด push ให้ปิดสวิตช์")

    value = {"enabled": bool(enabled), "start": start, "end": end}

    async with pool.acquire() as conn:
        async with conn.transaction():
            await require_permission_anywhere(conn, user_id, PERMISSION)

            # อ่านของเดิมใน transaction เดียวกัน + `FOR UPDATE` กันสองคำขอเขียนทับกันแล้ว
            # audit บันทึก old_values ผิด (แถวอาจยังไม่มี = old_values เป็น None)
            before = await conn.fetchrow(
                "SELECT value FROM app_settings WHERE key = $1 FOR UPDATE", QUIET_HOURS_KEY
            )

            await conn.execute(
                """
                INSERT INTO app_settings (key, value, description, updated_by)
                VALUES ($1, $2::jsonb, $3, $4)
                ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = NOW()
                """,
                QUIET_HOURS_KEY,
                json.dumps(value),
                "ช่วงเวลาที่ไม่ส่ง push ทั้งโรงเรียน (A8)",
                user_id,
            )

            await AuditLogger("app_settings_service").log(
                conn=conn,
                action="UPDATE_QUIET_HOURS",
                actor_identifier=str(user_id),
                client_source="web",
                user_id=user_id,
                entity_type="app_setting",
                # entity_id เป็น VARCHAR ⇒ ใช้ key ได้ตรง ๆ (ตารางนี้ไม่มี id เลข)
                entity_id=QUIET_HOURS_KEY,
                old_values={"quiet_hours": normalize_quiet_hours(before["value"] if before else None)},
                new_values={"quiet_hours": value},
            )

        return await fetch_quiet_hours(conn)
