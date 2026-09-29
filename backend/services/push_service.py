"""
📲 Web Push Service (A3)
========================
**ที่เดียวในโปรเจคที่ถือ SQL ของ Web Push** — router และ worker เรียกผ่านที่นี่

สถาปัตยกรรม (ดูเหตุผลเต็มใน `migrations/018_push_notifications.py`):
    notifications INSERT ──trigger──▶ push_outbox ──worker claim──▶ ส่ง HTTP ──▶ FCM/APNs

⭐ **ทำไมต้องมี outbox คั่นกลาง ไม่ยิงจาก trigger ตรง ๆ:**
   1. งาน push ต้องออก **นอก** transaction ของ caller — trigger ไม่ทำได้
      (การยิง HTTP ไป Google/Apple ใช้เวลาเป็นร้อย ms; ถ้าทำใน trigger จะล็อก
      แถวใน `notifications` ไว้ตลอดเวลาที่รอ network ⇒ ทั้งระบบช้า)
   2. ต้อง retry ได้เมื่อปลายทางล่ม โดยไม่ต้องมี state ในหน่วยความจำ
      (worker restart = หายหมด)
   3. ต้องมีเพดานกัน "push storm" เมื่อ worker ล่มไปหลายชั่วโมง

⭐ **เลือกประกอบ VAPID/ECE เองจาก 2 ไลบรารี แทน `pywebpush`** โดยเจตนา:
   `pywebpush==2.5.0` ลาก **20 แพ็กเกจ** รวม HTTP client อีกสองชุดที่ไม่มีโค้ดไหนใช้
   (`requests` + `aiohttp`) — ทั้งที่โปรเจคมี `httpx` อยู่แล้ว
   ⇒ `http-ece` + `py-vapid` พึ่งแค่ `cryptography` ที่ pin อยู่แล้ว ⇒ **transitive = 0**

⚠️ **กับดักที่ต้องรู้ก่อนแก้ไฟล์นี้:**
   - `http_ece.encrypt()` รับ `dh` / `auth_secret` เป็น **bytes ที่ decode แล้ว**
     ไม่ใช่สตริง base64url — ส่งสตริงไปจะพังแบบเงียบ
   - ephemeral key ต้อง **สร้างใหม่ทุกข้อความ** ห้าม reuse
   - `Vapid02.sign()` ต้องการ `aud` ที่มี scheme+host (py-vapid validate รูปแบบ)
   - **ห้ามถือ DB connection ระหว่างยิง HTTP** — claim แล้วคืน connection ก่อน
     (ดูคอมเมนต์ใน `process_pending`)
"""
import asyncio
import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import http_ece
import httpx
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid02

from core.config import settings
from services.app_settings_service import (
    get_quiet_hours,
    quiet_hours_active,
    quiet_hours_resumes_at,
)

logger = logging.getLogger("PUSH")

# ปลายทางเริ่มต้นของ notification — ใช้เมื่อคำนวณ deep link ไม่ได้
# ⚠️ ต้องเป็น `/app/notifications` **ไม่ใช่** `/notifications` — router ของ frontend
#    มี redirect แบบ string ที่ทำ query หลุด (ดูกับดักในแผน §20.8)
DEFAULT_PUSH_URL = "/app/notifications"

# ── A4 (deep link) — ปลายทางจริงของแต่ละ notification ─────────────────────────
# ⚠️ **ต้องตรงกับ `NotificationCenter.go()`** (`frontend/src/views/notifications/NotificationCenter.vue`)
#    ไม่งั้นผู้ใช้จะเจอสองพฤติกรรม: กดในแอปไปที่หนึ่ง กดจาก push ไปอีกที่หนึ่ง
#    ซึ่งเป็นความไม่สม่ำเสมอที่หาสาเหตุยาก เพราะทั้งสองทาง "ดูเหมือนถูก" แยกกัน
#    ⇒ เทสต์ `test_T16d_*` ตรึงลำดับการตัดสินไว้ — **อย่าสลับลำดับ**
BOARD_REPORTS_URL = "/app/boards/reports"

# ── E2 (ประกาศฉุกเฉิน) — ปลายทางคือ **หน้า Home** ไม่ใช่หน้ารวมแจ้งเตือน ────────
# ประกาศโรงเรียนถูกแสดงบน Home (บล็อกประกาศ ไม่มี LIMIT) ⇒ กด push แล้วควรไปเห็น
# ตัวประกาศเลย ไม่ใช่ไปดูรายการแจ้งเตือนที่ต้องกดต่ออีกที
# ✅ **สองทางตรงกันแล้ว** — ฝั่งแอปมีกฎเดียวกันที่ `router/deepLink.ts` (`{ name: 'home' }`)
#    ซึ่ง `NotificationCenter.go()` เรียกใช้ ⇒ push กับปุ่มในแอปพาไปที่เดียวกัน
#    · ตรึงด้วยเทสต์ **สองภาษา**: `test_T21i` + `_DEEP_LINK_CASES` (ที่นี่) กับ
#      `deepLink.spec.ts` D10/D11 (ฝั่ง FE) · ส่วน `test_T21h`/`D3` เป็นด่านกัน
#      "เพิ่มกลุ่มใหม่แล้วลืมนิยามปลายทาง" ทั้งสองฝั่ง
ANNOUNCEMENT_URL = "/app/home"

# เวลารอสูงสุดต่อ 1 คำขอ — FCM/APNs ปกติตอบใน <1 วิ, 10 วิคือ "ปลายทางตายแล้ว"
_SEND_TIMEOUT_SECONDS = 10.0

# ค่า `Urgency` ที่ RFC 8030 §5.3 นิยามไว้ — **มีแค่ 4 ตัวนี้** ค่าอื่นผู้ให้บริการตอบ 400
_URGENCIES = frozenset({"very-low", "low", "normal", "high"})


def _urgency() -> str:
    """`Urgency` ของข้อความนี้ — กรองค่าจาก `.env` ก่อนปล่อยออกเน็ต

    ⚠️ **ทำไมต้องกรอง ไม่ส่งค่าดิบ ๆ:** ค่าที่ผิดจะได้ **400 จากผู้ให้บริการ**
       ⇒ `_classify` ตัดสินเป็น `permanent` ⇒ push **ตายทุกอัน** โดยที่ in-app ยังทำงาน
       = อาการ "เปิด push แล้วแต่ไม่มีอะไรเด้งเลย" ซึ่งหาสาเหตุยากมาก
       (ค่า default ของ pydantic Settings คือ `str` ⇒ `.env` เขียนอะไรลงไปก็ผ่านเข้ามาได้)

    ค่าที่ผิด → เตือนใน log แล้วใช้ `high` ต่อ (เลือก `high` ไม่ใช่ `normal` เพราะ
    อาการของ `normal` คือ "เงียบ" ซึ่งผู้ใช้ตีความว่า "พัง" และเราไม่รู้ตัว)
    """
    value = (settings.PUSH_URGENCY or "").strip().lower()
    if value in _URGENCIES:
        return value
    logger.warning(
        f"⚠️ PUSH_URGENCY={settings.PUSH_URGENCY!r} ไม่ใช่ค่าที่ RFC 8030 นิยาม "
        f"({sorted(_URGENCIES)}) — ใช้ 'high' แทน"
    )
    return "high"


# ============================================================
# 🔑 VAPID — โหลดคีย์แบบ lazy + cache
# ============================================================

_cached_vapid: Optional[Vapid02] = None
_cached_private_key: Optional[str] = None


def push_enabled() -> bool:
    """มีคีย์ครบไหม — **ไม่มีคีย์ = ปิด push ทั้งระบบ** (in-app ยังทำงานปกติ)

    ⭐ นี่คือสวิตช์ปิดฉุกเฉินที่ไม่ต้อง deploy โค้ด: ลบค่าสองตัวออกจาก `.env`
       แล้ว `docker service update --force` ⇒ worker จะ mark outbox เป็น
       `vapid-not-configured` แล้วหยุดยิง (ไม่ปล่อยให้คิวโตไม่หยุด)
    """
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def _vapid() -> Vapid02:
    """โหลด Vapid02 จาก settings — cache ตามค่าคีย์ (เปลี่ยนค่าใน .env แล้วโหลดใหม่)

    ⚠️ cache ตาม **ค่า** ไม่ใช่ cache ครั้งเดียวตลอดโปรเซส เพราะเทส monkeypatch
       `settings.VAPID_PRIVATE_KEY` — ถ้า cache แบบครั้งเดียว เทสต์จะได้คีย์ของเทสก่อนหน้า
    """
    global _cached_vapid, _cached_private_key
    key = settings.VAPID_PRIVATE_KEY
    if _cached_vapid is None or _cached_private_key != key:
        # `from_string` strip whitespace → base64url decode → 32 byte = สเกลาร์ล้วน
        # (รูปเดียวกับที่ scripts/generate_vapid_keys.py พิมพ์ออกมา)
        _cached_vapid = Vapid02.from_string(key)
        _cached_private_key = key
    return _cached_vapid


def _reset_vapid_cache() -> None:
    """ให้เทสต์ล้าง cache ได้หลัง monkeypatch settings"""
    global _cached_vapid, _cached_private_key
    _cached_vapid = None
    _cached_private_key = None


# ============================================================
# 🔐 ECE — เข้ารหัส payload ตาม RFC 8188/8291
# ============================================================

def _repad(b: bytes) -> bytes:
    """base64url ที่เบราว์เซอร์ส่งมา **ไม่มี padding** — เติมก่อน decode

    (สูตรเดียวกับ `pywebpush._repad` — เติมให้ความยาวหาร 4 ลงตัว)
    """
    return b + b"===="[: len(b) % 4]


def _decode_key(s: str) -> bytes:
    """base64url string → bytes

    ⚠️ `http_ece.encrypt()` ต้องการ **bytes** ไม่ใช่สตริง — ถ้าส่งสตริงไปจะพังแบบเงียบ
       (ไม่มี error ที่สื่อความหมาย) นี่คือกับดักอันดับต้น ๆ ของไฟล์นี้
    """
    return base64.urlsafe_b64decode(_repad(s.encode()))


# ============================================================
# 🧱 Payload builder — pure function (เทสง่าย ไม่ต้องมี DB/network)
# ============================================================

def _field(row: Any, key: str) -> Any:
    """อ่านคีย์จาก row ที่อาจเป็น `asyncpg.Record` **หรือ** `dict` — คืน `None` ถ้าไม่มี

    ⚠️ จำเป็นจริง ไม่ใช่ความระแวง: เทสต์หลายตัวส่ง `dict` เปล่า ๆ ที่ไม่มีคีย์ครบ
       (เช่น `test_T16b` ส่ง row ที่ไม่มี `group_type`) และ row จาก SQL จริงก็เพิ่ม/ลด
       คอลัมน์ได้โดยไม่ต้องแก้ทุก call site ⇒ ถ้าใช้ `row[key]` ตรง ๆ จะได้ `KeyError`
       ที่โผล่เป็น "push ตายทั้งระบบ" ไม่ใช่ "เทสต์พังหนึ่งตัว"
    """
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def _deep_link_url(row: Any) -> str:
    """ปลายทางเมื่อผู้ใช้กด notification — **ฟังก์ชันบริสุทธิ์**

    ลำดับการตัดสินลอกจาก `NotificationCenter.go()` ตรง ๆ (5 ขั้น) — **ลำดับมีความหมาย**:

      1. กลุ่ม `report` + ชนิด `report_new` → **คิวรายงาน** (`/app/boards/reports`)
         ★ ต้องมาก่อนข้อ 3 เพราะ notification นี้พก `board_id` มาด้วย — ถ้าตกไปข้อ 3
         จะพาสภาฯ ไปที่ตัวบอร์ด แทนที่จะพาไป "คิวที่ต้องลงมือ" ซึ่งเป็นเหตุผลที่แจ้ง
      2. กลุ่ม `report` ชนิดอื่น ที่มี `board_id` → **บอร์ดนั้น** (`report_actioned`
         ส่งถึง *ผู้แจ้ง* ซึ่งอาจเป็นนักเรียน — ต้องไปดูบอร์ด ไม่ใช่คิวของสภา)
      3. กลุ่ม `announcement` (E2) → **Home** (`/app/home`) ซึ่งเป็นที่แสดงตัวประกาศ
      4. `entity_type == 'issue'` + `entity_id` → **หน้ารายละเอียดเรื่อง**
      5. มี `board_id` → **หน้าบอร์ด**

    ไม่เข้าเงื่อนไขใด → `/app/notifications` (ปลอดภัยเสมอ: ไม่พาไปที่ที่ไม่มีอยู่)

    ⚠️ **ห้ามใส่ `report_new` ไว้หลังข้อ 3** — ทั้งสองชนิดมี `board_id` เหมือนกัน
       การสลับลำดับจะเปลี่ยนปลายทางของ `report_new` โดยที่เทสต์ที่ assert แค่
       "มี url" จะไม่จับได้

    ⚠️ **ข้อ 3 ต้องไม่ผูกกับ `entity_id`** — ประกาศแสดงทั้งก้อนบน Home ไม่ได้เจาะจงใบ
       ⇒ แม้ `entity_id` เป็น NULL ก็ต้องได้ `/app/home` (ตรึงด้วย `test_T21i` เคสที่ 2)
       ต่างจากข้อ 4 ที่ *ต้อง* มี `entity_id` ไม่งั้นจะได้ `/app/issues/None`
    """
    group_type = _field(row, "group_type")
    notif_type = _field(row, "type")
    entity_type = _field(row, "entity_type")
    entity_id = _field(row, "entity_id")
    board_id = _field(row, "board_id")

    if group_type == "report":
        if notif_type == "report_new":
            return BOARD_REPORTS_URL
        if board_id is not None:
            return f"/app/boards/{board_id}"
        return DEFAULT_PUSH_URL

    # 5. ประกาศฉุกเฉิน (E2) → Home ซึ่งเป็นที่แสดงตัวประกาศ
    #    ★ มาก่อนข้อ 3/4 โดยไม่จำเป็นต้องมี เพราะ announcement ไม่มี entity_type='issue'
    #      และไม่มี board_id — แต่วางไว้ให้ชัดว่าเป็นกฎ *เจตนา* ไม่ใช่การตกหล่นไป fallback
    if group_type == "announcement":
        return ANNOUNCEMENT_URL

    if entity_type == "issue" and entity_id is not None:
        return f"/app/issues/{entity_id}"

    if board_id is not None:
        return f"/app/boards/{board_id}"

    return DEFAULT_PUSH_URL


def build_payload(row: Any) -> Dict[str, Any]:
    """สร้าง payload ของ notification 1 อัน — **ฟังก์ชันบริสุทธิ์**

    แยกออกมาเป็น pure function โดยเจตนา: รูป payload คือสัญญาระหว่าง backend กับ
    `sw.js` (ซึ่งอ่าน `event.data.json()`) ⇒ ถ้าที่นี่เปลี่ยนชื่อคีย์ `sw.js` จะพัง
    โดยไม่มีอะไรจับได้ในฝั่ง Python · การเป็น pure function ทำให้เทสต์ยิงตรงได้

    คีย์ที่ `sw.js` อ่านจริง (ดู `frontend/public/sw.js`):
      - `title`, `body` → เนื้อ notification
      - `tag`           → ให้ notification ใหม่ *แทนที่* อันเก่าของเรื่องเดียวกัน
                          (ไม่ให้มือถือขึ้นซ้ำ 5 อันเมื่อมีคนตอบรัว ๆ)
      - `data.url`      → ปลายทางเมื่อคลิก — **คำนวณจาก `_deep_link_url()`** (A4)
                          ไม่ใช่ค่าคงที่อีกต่อไป

    คีย์อื่นใน `data` (`notification_id`/`type`/`entity_type`/`entity_id`/`board_id`)
    ยังส่งต่อไปเหมือนเดิม — `sw.js` ไม่ได้ใช้ แต่มันคือสัญญาที่เปิดให้ฝั่ง client
    ตัดสินใจเองได้ในอนาคต (เช่น เลือกยิง analytics หรือรวม notification)
    """
    return {
        "title": row["title"],
        "body": row["body"],
        "tag": f"piri-notif-{row['notification_id']}",
        "data": {
            "url": _deep_link_url(row),
            "notification_id": row["notification_id"],
            "type": row["type"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "board_id": row["board_id"],
        },
    }


# ============================================================
# 🌐 ตัวส่งจริง — injectable เพื่อให้เทสต์ไม่ต้องออกเน็ต
# ============================================================

async def _send_one(
    client: httpx.AsyncClient,
    sub: Dict[str, Any],
    payload: Dict[str, Any],
    *,
    ttl: int,
) -> Optional[int]:
    """ส่ง 1 push → คืน HTTP status (หรือ `None` ถ้า network ล่ม)

    ⚠️ ลำดับในฟังก์ชันนี้สำคัญ — VAPID ต้องเซ็น **ก่อน** เข้ารหัส ไม่งั้น `aud`
       จะไม่ตรงกับ endpoint ที่จะยิงไป
    """
    data = json.dumps(payload, ensure_ascii=False).encode()
    u = urlparse(sub["endpoint"])

    # ① VAPID JWT (RFC 8292)
    #    `Vapid02.sign()` คืน {"Authorization": "vapid t=<jwt>,k=<pubkey>"}
    #    - `aud` = scheme://netloc ของ **endpoint ปลายทาง** (ต้องตรงเป๊ะ ไม่งั้นผู้ให้บริการปฏิเสธ)
    #      ⇒ ห้าม hardcode เป็น fcm.googleapis.com เพราะ Mozilla/Apple ใช้ aud คนละค่า
    #    - `exp` 12 ชม. — เลียนแบบ pywebpush (มีเวลาเหลือพอแม้ retry หลายรอบ)
    #    - `sub` ต้องมาจาก settings (py-vapid validate ว่าต้องเป็น mailto: หรือ URL)
    headers = _vapid().sign({
        "sub": settings.VAPID_SUBJECT,
        "aud": f"{u.scheme}://{u.netloc}",
        "exp": int(time.time()) + 12 * 3600,
    })

    # ② ECE (RFC 8188/8291) — ephemeral P-256 **ต่อข้อความ** ห้าม reuse
    body = http_ece.encrypt(
        data,
        salt=os.urandom(16),
        private_key=ec.generate_private_key(ec.SECP256R1()),
        dh=_decode_key(sub["p256dh"]),
        auth_secret=_decode_key(sub["auth"]),
        version="aes128gcm",
    )

    # ⚠️ ไม่ส่ง `Content-Type` — pywebpush ก็ไม่ส่ง (ปลายทางไม่ต้องการ และการใส่ค่าผิด
    #    อาจทำให้ผู้ให้บริการบางรายปฏิเสธ) · `Content-Length` httpx จัดการเอง
    #
    # 🚨 **`Urgency` (RFC 8030 §5.3) — ห้ามลบ** เป็นตัวตัดสินว่าเครื่องผู้ใช้จะเด้งทันที
    #    หรือจะกองไว้จนกว่าเขาจะเปิดแอพเอง
    #    · ไม่ส่ง header นี้ = `normal` ⇒ **FCM (Android) เลื่อนการส่งได้** จนกว่าเครื่องจะตื่น
    #      อาการที่เกิดขึ้นจริง: ปิดแอพอยู่เงียบ พอเปิดแอพทีเดียวเด้งมาทั้งกองเก่า
    #    · `high` ⇒ FCM ตื่นเครื่องทันที (APNs ก็ส่งแบบ immediate)
    #    · ค่าที่ถูกต้องมีแค่ 4 ตัว: `very-low` `low` `normal` `high` — ค่าอื่นผู้ให้บริการ
    #      อาจตอบ 400 ⇒ ต้องกรองก่อน ไม่ปล่อยค่าจาก .env ผ่านดิบ ๆ
    headers.update({
        "Content-Encoding": "aes128gcm",
        "TTL": str(ttl),
        "Urgency": _urgency(),
    })

    try:
        r = await client.post(sub["endpoint"], content=body, headers=headers)
        return r.status_code
    except httpx.HTTPError as e:
        # timeout / DNS / TLS — ถือเป็น retryable (คืน None แล้วให้ _classify ตัดสิน)
        logger.warning(f"⚠️ ส่ง push ไม่สำเร็จ (network): {type(e).__name__}: {e}")
        return None


def _classify(status: Optional[int]) -> str:
    """HTTP status → การกระทำ — **pure function**

    | status | ผล | ทำไม |
    |---|---|---|
    | 200–299 | `ok` | ส่งถึง |
    | 404 / 410 | `gone` | **อุปกรณ์นี้ตายแล้ว** (ถอนแอพ/ล้างข้อมูลเบราว์เซอร์) ⇒ ลบ subscription ทิ้ง |
    | 429 | `retry` | ผู้ให้บริการขอให้ช้าลง |
    | 400–499 อื่น | `permanent` | payload/key ผิด — ยิงซ้ำอีก 100 ครั้งก็ได้เรื่องเดิม |
    | 5xx / `None` | `retry` | ปลายทางหรือ network ล่มชั่วคราว |
    """
    if status is None:
        return "retry"
    if 200 <= status < 300:
        return "ok"
    if status in (404, 410):
        return "gone"
    if status == 429:
        return "retry"
    if 400 <= status < 500:
        return "permanent"
    return "retry"


# ============================================================
# ⚙️ ฝั่ง API — router เรียก (รับ pool)
# ============================================================

async def get_status(pool, user_id: int) -> dict:
    """สถานะ push ของผู้ใช้คนนี้ + public key ที่เบราว์เซอร์ต้องใช้ subscribe

    ⭐ **public key ต้องเสิร์ฟทาง endpoint ไม่ใช่ฝังตอน build frontend**
       เพราะ `docker build` ของ frontend ไม่อ่าน root `.env` (รับ build-arg ตัวเดียว
       คือ `VITE_API_BASE_URL`) ⇒ ถ้าฝังตอน build จะต้อง rebuild image ทุกครั้งที่ rotate key
       และ staging/production จะได้คีย์เดียวกันโดยแยกไม่ออก
    """
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM push_subscriptions WHERE user_id = $1", user_id
        )
    enabled = push_enabled()
    return {
        "enabled": enabled,
        # ส่งค่าว่างเมื่อปิด — อย่าส่งคีย์ออกไปทั้งที่ปิดใช้งาน
        "public_key": settings.VAPID_PUBLIC_KEY if enabled else "",
        "device_count": int(count or 0),
    }


async def save_subscription(
    pool, user_id: int, *, endpoint: str, p256dh: str, auth: str,
    user_agent: Optional[str] = None,
) -> None:
    """บันทึก/อัปเดตปลายทาง push ของอุปกรณ์นี้ — idempotent

    ⭐ **`SET user_id = EXCLUDED.user_id` คือบรรทัดที่กันการรั่วข้ามผู้ใช้**
       เครื่องเรียนเครื่องเดียวถูกใช้หลายคน (logout → login คนใหม่) เบราว์เซอร์จะส่ง
       endpoint เดิมกลับมา ⇒ ถ้าไม่ยึดเจ้าของใหม่ แถวจะยังเป็นของคนเก่า
       แล้ว **push ของคนใหม่จะไปโผล่บนเครื่องที่คนเก่าล็อกอินค้างไว้**
       — ดูเทสต์ S3 ซึ่งเป็นด่านความปลอดภัยของเรื่องนี้
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, user_agent)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (endpoint) DO UPDATE
                SET user_id = EXCLUDED.user_id,
                    p256dh = EXCLUDED.p256dh,
                    auth = EXCLUDED.auth,
                    user_agent = EXCLUDED.user_agent,
                    failure_count = 0,
                    updated_at = NOW()
            """,
            user_id, endpoint, p256dh, auth, user_agent,
        )


async def delete_subscription(pool, user_id: int, *, endpoint: str) -> int:
    """ลบปลายทางของอุปกรณ์นี้ — **คืนจำนวนแถวที่ลบจริง**

    ⚠️ `AND user_id = $1` **ห้ามลบขาด** — ถ้าไม่มี ผู้ใช้คนใดก็ลบ subscription
       ของคนอื่นได้เพียงรู้ endpoint (ซึ่งรั่วได้ทาง log/proxy) — ดูเทสต์ S4
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM push_subscriptions WHERE user_id = $1 AND endpoint = $2",
            user_id, endpoint,
        )
    return int(result.split()[-1])


# ============================================================
# 🏃 ฝั่ง worker
# ============================================================

async def _claim(pool, batch_size: int) -> List[Dict[str, Any]]:
    """จองแถวออกจากคิว — transaction สั้น **แล้ว commit ก่อนยิง HTTP**

    ⭐ `FOR UPDATE SKIP LOCKED` ทำให้หลาย worker/replica ทำงานพร้อมกันได้โดยไม่มี
       แถวซ้ำ (worker ที่สองข้ามแถวที่ถูกล็อกอยู่ ไปหยิบแถวถัดไป)
    ⚠️ `processing_at IS NULL` จำเป็น: ระหว่างที่ worker หนึ่งกำลังส่งอยู่ แถวยังมี
       `processed_at IS NULL` และ `next_attempt_at <= NOW()` ⇒ ถ้าไม่กรอง worker
       อีกตัวจะหยิบไปส่ง **ซ้ำ** (ผู้ใช้ได้ push สองอัน)
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                UPDATE push_outbox
                   SET processing_at = NOW(), attempts = attempts + 1
                 WHERE id IN (
                     SELECT id FROM push_outbox
                      WHERE processed_at IS NULL
                        AND processing_at IS NULL
                        AND next_attempt_at <= NOW()
                      ORDER BY id
                      LIMIT $1
                      FOR UPDATE SKIP LOCKED
                 )
                 RETURNING id, notification_id, user_id, attempts
                """,
                batch_size,
            )
    return [dict(r) for r in rows]


async def _load_payloads(pool, outbox_ids: List[int]) -> List[Dict[str, Any]]:
    """ดึง payload + ปลายทางของทุกแถวที่จองไว้ — **คิวรีเดียวต่อ batch**

    ⚠️ `LEFT JOIN push_subscriptions` โดยเจตนา: ผู้ใช้ที่ยังไม่เคยกดเปิด push
       จะได้ `subscription_id IS NULL` แล้วถูก mark processed ทันที (ไม่ค้างในคิว)
       ถ้าใช้ INNER JOIN แถวนั้นจะ **หายไปจากผลลัพธ์** แล้วค้าง pending ตลอดกาล
       (เทสต์ T8 จับเรื่องนี้)

    ⚠️ ผู้ใช้ที่มี 3 อุปกรณ์จะได้ 3 แถวสำหรับ outbox 1 อัน → caller ต้อง group เอง
    """
    if not outbox_ids:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT o.id            AS outbox_id,
                   o.attempts      AS attempts,
                   o.notification_id,
                   o.user_id,
                   n.type, n.title, n.body,
                   -- ⭐ A4: `group_type` ต้องมาก่อน `type` ในการตัดสิน deep link
                   --    (report_new ต้องไปคิวรายงาน ไม่ใช่ไปบอร์ด) — ดู `_deep_link_url()`
                   n.group_type,
                   n.entity_type, n.entity_id, n.board_id,
                   -- ⭐ E2 (migration 024): ธงยกเว้น quiet hours รายแถว — ประกาศฉุกเฉินตั้ง TRUE
                   --    ⚠️ ต้อง SELECT มาที่นี่เพราะด่าน quiet hours อยู่ใน `process_pending`
                   --       ซึ่งทำงาน *หลัง* คิวรีนี้ และต้องรู้รายแถวว่าใครได้ยกเว้น
                   --    ⚠️ เป็น LEFT JOIN อยู่แล้ว ⇒ ไม่เพิ่ม JOIN ใหม่ ไม่เพิ่มต้นทุน
                   n.bypass_quiet_hours,
                   n.created_at    AS notification_created_at,
                   s.id            AS subscription_id,
                   s.endpoint, s.p256dh, s.auth
              FROM push_outbox o
              JOIN notifications n ON n.id = o.notification_id
              LEFT JOIN push_subscriptions s ON s.user_id = o.user_id
             WHERE o.id = ANY($1::bigint[])
             ORDER BY o.id
            """,
            outbox_ids,
        )
    return [dict(r) for r in rows]


async def _finish(pool, ids: List[int], *, error: Optional[str] = None) -> None:
    """ปิดแถวว่า "จบแล้ว" (ไม่ว่าจะสำเร็จหรือทิ้ง)"""
    if not ids:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE push_outbox
               SET processed_at = NOW(), processing_at = NULL, last_error = $2
             WHERE id = ANY($1::bigint[])
            """,
            ids, error,
        )


async def _retry_later(pool, ids: List[int], *, error: str) -> tuple:
    """คืนแถวเข้าคิวพร้อม backoff — `30 * 2^attempts` วินาที เพดาน 1 ชม.

    คืน `(rescheduled, exhausted)` — **ต้องแยกสองจำนวนนี้ ไม่ใช่คืน len(ids)**
    (เวอร์ชันแรกคืน `None` แล้ว caller ใช้ `len(retry_ids)` ⇒ `stats["retry"]` นับ
    แถวที่ **ยอมแพ้ไปแล้ว** รวมเข้าไปด้วย · worker จึง log ว่า "เลื่อนส่ง" ทั้งที่
    push ถูกทิ้งถาวร — อันตรายเพราะคนเฝ้าระบบจะไม่เห็นว่ามีของหาย)

    ⚠️ ต้องล้าง `processing_at` ด้วย ไม่งั้นแถวจะค้าง (ไม่มีใครหยิบได้อีก)
    """
    if not ids:
        return (0, 0)
    max_attempts = settings.PUSH_MAX_ATTEMPTS
    async with pool.acquire() as conn:
        # แถวที่ลองครบเพดานแล้ว → ปิดเป็น "จบ" ไม่ retry อีก
        exhausted = await conn.fetch(
            "SELECT id FROM push_outbox WHERE id = ANY($1::bigint[]) AND attempts >= $2",
            ids, max_attempts,
        )
        exhausted_ids = [r["id"] for r in exhausted]
        remaining = [i for i in ids if i not in set(exhausted_ids)]

        if exhausted_ids:
            await conn.execute(
                """
                UPDATE push_outbox
                   SET processed_at = NOW(), processing_at = NULL,
                       last_error = COALESCE(last_error, '') || ' | max-attempts'
                 WHERE id = ANY($1::bigint[])
                """,
                exhausted_ids,
            )
        if remaining:
            await conn.execute(
                """
                UPDATE push_outbox
                   SET processing_at = NULL,
                       last_error = $2,
                       next_attempt_at = NOW() + (
                           LEAST(30 * POWER(2, attempts), 3600) * INTERVAL '1 second'
                       )
                 WHERE id = ANY($1::bigint[])
                """,
                remaining, error,
            )
    return (len(remaining), len(exhausted_ids))


async def delete_subscriptions_by_id(pool, ids: List[int]) -> int:
    """ลบ subscription ที่ปลายทางยืนยันแล้วว่าตาย (HTTP 404/410)

    ลบ **ก่อน** mark outbox ว่าจบ — ถ้าลบไม่สำเร็จ ปลายทางที่ตายจะถูกยิงซ้ำทุกครั้ง
    """
    if not ids:
        return 0
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM push_subscriptions WHERE id = ANY($1::int[])", ids
        )
    return int(result.split()[-1])


async def _mark_subscription_health(pool, *, ok_ids: List[int],
                                    failed_ids: List[int]) -> None:
    """จดสุขภาพของปลายทาง — `last_success_at` / `failure_count`

    ⚠️ **คอลัมน์สองตัวนี้มีมาตั้งแต่ migration 018 แต่ไม่มีโค้ดไหนเขียนเลยทั้งรอบ**
       ⇒ เปิดตารางดูก็ตอบไม่ได้ว่าอุปกรณ์ไหนยังทำงานอยู่จริง (ต้องไปไล่เดาจาก outbox)
       ⇒ เป็นหนี้ที่ทำให้ "วัดผลหลัง deploy" ทำไม่ได้ และวินิจฉัยเคส
       "push ไม่เด้งบนเครื่องนี้" ไม่ได้เลย — ต้องปิด

    ยิง **2 คำสั่งต่องวด ไม่ใช่ต่ออุปกรณ์** (`= ANY(...)`) — fanout 1,000 เครื่อง
    ก็ยังเป็น 2 คำสั่ง · ข้ามไปเลยถ้าลิสต์ว่าง (ไม่เปิด connection ทิ้งเปล่า)

    ความหมายที่ตกลง:
      - `ok` → `last_success_at = NOW()` **และรีเซ็ต `failure_count = 0`**
        (ล้มติดกัน 3 ครั้งแล้วสำเร็จ = ปลายทางยังดี ไม่ควรถูกลงโทษจากอดีต)
      - ล้มเหลว (`retry`/`permanent`) → `failure_count += 1` · **ไม่แตะ `last_success_at`**
      - `gone` (404/410) → **ไม่นับ** เพราะแถวถูกลบไปแล้ว (นับไปก็ไม่มีใครดู)
    """
    if not ok_ids and not failed_ids:
        return
    async with pool.acquire() as conn:
        if ok_ids:
            await conn.execute(
                """
                UPDATE push_subscriptions
                   SET last_success_at = NOW(), failure_count = 0, updated_at = NOW()
                 WHERE id = ANY($1::int[])
                """,
                ok_ids,
            )
        if failed_ids:
            await conn.execute(
                """
                UPDATE push_subscriptions
                   SET failure_count = failure_count + 1, updated_at = NOW()
                 WHERE id = ANY($1::int[])
                """,
                failed_ids,
            )


async def process_pending(pool, *, sender=None) -> Dict[str, int]:
    """ประมวลผลคิว 1 รอบ — หัวใจของ worker

    `sender` injectable (default = `_send_one`) เพื่อให้ **เทสต์ไม่ต้องออกเน็ตเลย**
    (plan §20.14 ข้อ 6: ห้ามมีเทสต์ที่ยิง HTTP จริง)

    ⚠️ **ห้ามถือ DB connection ระหว่างยิง HTTP** — ลำดับคือ
       claim (tx สั้น) → คืน connection → ยิง HTTP → เปิด tx ใหม่เพื่อจดผล
       ถ้าถือ connection ไว้ 20 วิระหว่างส่ง 1,000 push จะกิน pool ของทั้งระบบ
       (backend ใช้ pool เดียวกัน — ผู้ใช้จริงจะโดน 500 เพราะ pool หมด)

    นโยบายหลายอุปกรณ์ (ตัดสินแล้ว — ดูแผน §20.6):
      - สำเร็จ **อย่างน้อย 1** เครื่อง → ปิดแถว (ยอมให้อีกเครื่องพลาด; in-app ยังครอบคลุม)
      - ล้มเหลวทั้งหมด + retryable → retry **ทั้งแถว** (push ซ้ำดีกว่า push หาย)
      - ไม่ทำ per-subscription retry — ต้องมีตาราง state ต่ออุปกรณ์ เกินความจำเป็นของ A3
    """
    stats = {"claimed": 0, "sent": 0, "gone": 0, "retry": 0,
             "dropped": 0, "skipped": 0, "stale": 0, "quiet": 0}

    claimed = await _claim(pool, settings.PUSH_BATCH_SIZE)
    stats["claimed"] = len(claimed)
    if not claimed:
        return stats

    ids = [c["id"] for c in claimed]

    # ⭐ ด่านที่ 9: ไม่มีคีย์ VAPID → **ต้องปิดแถวทิ้ง** ไม่ใช่ return เฉย ๆ
    #    ถ้า return เฉย ๆ คิวจะโตไม่หยุด (ผู้ใช้กดสร้างเรื่องทุกวัน แต่ไม่มีใครเก็บกวาด)
    if not push_enabled():
        await _finish(pool, ids, error="vapid-not-configured")
        stats["skipped"] = len(ids)
        logger.warning("⚠️ VAPID ไม่ได้ตั้งค่า — ปิด %d แถวในคิวโดยไม่ส่ง", len(ids))
        return stats

    rows = await _load_payloads(pool, ids)

    # --- จัดกลุ่มตาม outbox (1 outbox = 1 notification = N อุปกรณ์) ---
    grouped: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        g = grouped.setdefault(r["outbox_id"], {"subs": [], "meta": r})
        if r["subscription_id"] is not None:
            g["subs"].append({
                "id": r["subscription_id"],
                "endpoint": r["endpoint"],
                "p256dh": r["p256dh"],
                "auth": r["auth"],
            })

    # --- คัดแยก : ไม่มีอุปกรณ์ / เก่าเกินกำหนด ---
    no_device: List[int] = []
    stale: List[int] = []
    to_send: List[Dict[str, Any]] = []
    max_age = settings.PUSH_MAX_AGE_MINUTES
    now = time.time()

    for oid, g in grouped.items():
        if not g["subs"]:
            no_device.append(oid)
            continue
        created = g["meta"]["notification_created_at"]
        if created is not None and (now - created.timestamp()) > max_age * 60:
            # ⏰ กัน push storm: worker ล่ม 3 ชม. แล้วกลับมา — คิวมีแจ้งเตือนเก่า
            #    หลายพันอัน ถ้าส่งหมดผู้ใช้จะได้ push พรวดเดียวทั้งหน้าจอ
            stale.append(oid)
            continue
        to_send.append(g)

    if no_device:
        # ไม่มีอุปกรณ์ = ไม่มีอะไรต้องทำ (แต่ต้องปิดแถว ไม่งั้นค้างตลอดกาล)
        await _finish(pool, no_device)
        stats["skipped"] += len(no_device)
    if stale:
        await _finish(pool, stale, error="stale")
        stats["stale"] = len(stale)
        # 🚨 **ต้องเป็น WARNING ไม่ใช่ INFO** — การทิ้ง stale คือ **push ที่หายถาวร**
        #    ไม่มีใครได้รับแจ้งเตือน และไม่มี error ที่ไหนโผล่ให้เห็น
        #    (ต้นเหตุจริง 28 ก.ย. 2026: คิวท่วมด้วยงานที่ทำไม่ได้ ⇒ ของจริงไปถึงหัวคิว
        #     ตอนอายุ ~40 นาที ⇒ ถูกทิ้งเงียบ ๆ ทุกใบ — อาการ "แจ้งเตือนแค่ครั้งแรก")
        #    ถ้าบรรทัดนี้ไม่เคยขึ้น = ระบบปกติ · ถ้าขึ้น = **มีของหาย** ต้องดูทันที
        logger.warning(
            "⏰ ทิ้ง %d แจ้งเตือนที่ค้างเกิน %d นาที (ไม่ส่ง — กัน push storm) — "
            "ของเหล่านี้ **ไม่มีใครได้รับ** ควรดูว่าคิวตกค้างเพราะอะไร",
            len(stale), max_age,
        )

    # ==================== ⭐ A8: ด่าน quiet hours ====================
    # **ทำไมด่านอยู่ที่นี่ (หลัง no_device/stale) และไม่ใช่ที่อื่น:**
    #   1. **ไม่ใช่ตอนเข้าคิว** (ต่างจาก migration 019) — เพราะช่วงเวลาสิ้นสุดได้
    #      ถ้าตัดทิ้งตอน insert แถวนั้นจะ **ไม่มีวันถูกส่งเลย** แม้จะพ้นช่วงไปแล้ว
    #      ⇒ ที่นี่ตัดสิน "ตอนนี้ส่งได้ไหม" ซึ่งเป็นคำถามที่มีคำตอบต่างกันในแต่ละวินาที
    #   2. **ไม่ใช่การค้างแถวไว้ในคิว** (`next_attempt_at` เลื่อนออกไป) — จะไปชนด่าน
    #      `PUSH_MAX_AGE_MINUTES` ที่ตัดของเก่าทิ้ง ⇒ **ทุกแถวที่ค้างจะถูกทิ้ง**
    #      ตอนพ้นช่วงพอดี ⇒ ได้ 0 push · **แถวใน `notifications` คือบันทึกถาวรอยู่แล้ว**
    #      ⇒ การปิดแถวในคิวไม่ได้ทำให้ใคร "พลาด" อะไร (in-app + badge ยังครบ)
    #   3. **หลัง `stale`** เพื่อให้ `stats["quiet"]` มีความหมายว่า
    #      "จำนวนที่ **ถ้าถึงคิวก็จะได้ส่งจริง** แต่ถูกความเงียบกลืน" — ถ้านับรวม
    #      แถวที่ไม่มีอุปกรณ์/เก่าเกิน ตัวเลขนี้จะพองจนอ่านไม่ออกว่ากระทบใครจริง
    quiet: List[int] = []
    if to_send:
        # คิวรีเดียวต่อ batch และ **เฉพาะเมื่อมีของจะส่ง** ⇒ คิวว่าง = ไม่แตะ DB เพิ่มเลย
        quiet_config = await get_quiet_hours(pool)
        # ใช้ `now` **ค่าเดียวกัน** กับที่ตัดสิน stale — หนึ่ง batch = หนึ่งเวลาอ้างอิง
        # (ถ้าเรียก `time.time()` ใหม่ ของสองแถวใน batch เดียวกันอาจถูกตัดสินคนละวินาที)
        if quiet_hours_active(quiet_config, now=datetime.fromtimestamp(now, timezone.utc)):
            # ⭐ E2: ประกาศฉุกเฉิน (`bypass_quiet_hours = TRUE`) **ทะลุได้ทุกแถว**
            #    ⇒ เป็นข้อยกเว้น **รายแถว** ไม่ใช่รายกลุ่ม/รายผู้ใช้ ⇒ ต้องอ่านจาก meta
            #      ของแต่ละ outbox (ได้มาจาก JOIN ใน `_load_payloads`)
            quiet = [
                g["meta"]["outbox_id"] for g in to_send
                if not g["meta"].get("bypass_quiet_hours")
            ]
            to_send = [g for g in to_send if g["meta"].get("bypass_quiet_hours")]

            if quiet:
                await _finish(pool, quiet, error="quiet-hours")
                stats["quiet"] = len(quiet)
                resumes = quiet_hours_resumes_at(
                    quiet_config, now=datetime.fromtimestamp(now, timezone.utc)
                )
                # ℹ️ **INFO ไม่ใช่ WARNING** — ต่างจาก `stale` ข้างบน: นี่คือพฤติกรรม
                #    ที่ถูกออกแบบไว้ ไม่มีอะไรหาย (in-app ยังครบ) ⇒ ไม่ควรทำให้ log
                #    ดูเหมือนเหตุฉุกเฉิน ไม่งั้นของจริงจะจมอยู่ในความเท็จ
                #    ⚠️ ขึ้นเฉพาะเมื่อ **มีของถูกกลืนจริง** ไม่ใช่ทุก tick
                logger.info(
                    "🔇 quiet hours (%s–%s) — ระงับ %d แจ้งเตือน · จะกลับมาส่ง %s",
                    quiet_config["start"], quiet_config["end"],
                    len(quiet),
                    resumes.strftime("%d/%m %H:%M") if resumes else "—",
                )
                if to_send:
                    # E2: มีประกาศฉุกเฉินทะลุออกไปในรอบเดียวกัน — บันทึกแยกบรรทัด
                    # เพราะเป็นเหตุการณ์ที่ต้องตอบได้ว่า "ฉุกเฉินถึงมือใคร เมื่อไร"
                    logger.info(
                        "🚨 ประกาศฉุกเฉินทะลุ quiet hours %d รายการ (ธง bypass_quiet_hours)",
                        len(to_send),
                    )

    if not to_send:
        return stats

    # ==================== ยิง HTTP — ไม่ถือ DB connection ====================
    sem = asyncio.Semaphore(settings.PUSH_SEND_CONCURRENCY)
    ttl = settings.PUSH_TTL_SECONDS
    results: List[Dict[str, Any]] = []
    dead_sub_ids: set = set()
    ok_sub_ids: set = set()
    failed_sub_ids: set = set()

    async with httpx.AsyncClient(timeout=_SEND_TIMEOUT_SECONDS) as client:
        send = sender or _send_one

        async def one(g: Dict[str, Any], sub: Dict[str, Any], payload: Dict[str, Any]):
            """ยิง 1 ปลายทาง — **ต้องไม่โยนออกไปไหน** คืน `status=None` แทน

            🚨 **นี่คือด่านที่เคยรั่ว (29 ก.ย. 2026)** — อาการจริงบน staging:
               `logger.exception("❌ sender โยน exception")` ขึ้นพร้อม
               `binascii.Error: Invalid base64-encoded string` (คีย์ปลอมใน DB)
               แล้ว **ตัวนับเป็น 0 หมด** `claimed=1 sent=0 gone=0 retry=0 dropped=0`
               และแถวนั้น **ค้าง `processing_at` ไม่มีใครหยุด** จนกว่าจะ redeploy

            **ทำไมร้ายแรงกว่าที่เห็น:** exception ที่หลุดจาก `one()` ทำให้
            `asyncio.gather(return_exceptions=True)` คืน *exception* แทน tuple
            ⇒ `g` (ซึ่งผูก outbox_id) **หายไปทั้งก้อน** ⇒ ปลายทางที่จับผลต้องเดา
            ⇒ เขียน `outbox_id: None` ⇒ ถูก `continue` ข้ามในลูป `per_outbox`
            ⇒ **แถวไม่ถูกจัดประเภทเลย** — ไม่จบ ไม่ retry ไม่มีใครรู้

            ⇒ จับที่ **นี่** ไม่ใช่ที่ `_send_one` เพราะต้องคง `g`/`sub` ไว้จับผลให้ถูกแถว
               และต้องครอบ **ทุก** exception (crypto ใน `_send_one` ไม่ใช่ `httpx.HTTPError`
               ⇒ `except httpx.HTTPError` ที่นั่นจับไม่ได้) รวมถึง `sender` ที่เทสต์ฉีดเข้ามา
            ⇒ `_classify(None) == "retry"` ⇒ เข้าเส้น retry/`PUSH_MAX_ATTEMPTS`/`dropped`
               ตามปกติ ⇒ ล้มเหลวแบบมีตัวนับ ไม่ใช่แบบเงียบ

            ⚠️ `except Exception` **ไม่จับ `CancelledError`** (เป็น `BaseException`)
               ⇒ ตอน shutdown การยกเลิกยังทะลุผ่านตามเดิม — ตั้งใจ ไม่ใช่การมองข้าม
            """
            try:
                async with sem:
                    status = await send(client, sub, payload, ttl=ttl)
                return g, sub, status
            except Exception as e:
                # ⚠️ ห้าม log `sub["endpoint"]` — มันมี token ของอุปกรณ์อยู่ในตัว
                #    (netloc พอบอกได้ว่าเป็นผู้ให้บริการรายไหน โดยไม่รั่วความลับ)
                logger.exception(
                    "❌ sender โยน exception (outbox=%s sub=%s host=%s): %s",
                    g["meta"]["outbox_id"], sub["id"],
                    urlparse(sub["endpoint"]).netloc, type(e).__name__,
                )
                return g, sub, None

        tasks = [
            one(g, sub, build_payload(g["meta"]))
            for g in to_send for sub in g["subs"]
        ]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    for o in outcomes:
        if isinstance(o, BaseException):
            # ⚠️ มาถึงบรรทัดนี้ไม่ได้ในทางทฤษฎี — `one()` จับ `Exception` ไว้หมดแล้ว
            #    สิ่งที่เหลือคือ `BaseException` ที่ไม่ใช่ `Exception` = `CancelledError`
            #    ตอน shutdown ⇒ **ต้องทะลุผ่าน** ไม่ใช่กลืน (กลืนแล้ว lifespan จะรอค้าง)
            #
            # 🚨 **ห้ามเปลี่ยนเป็น `results.append({"outbox_id": None, …})` แบบเดิม**
            #    นั่นคือรูที่ทำให้แถวค้างถาวร (29 ก.ย. 2026) — `outbox_id: None`
            #    ไม่ผูกกับแถวไหนเลย ⇒ ถูกข้ามตอนจับกลุ่ม ⇒ ไม่มีใครปิดแถวให้
            #    ⇒ ถ้าจะรับมือ exception ที่ไม่รู้ว่าเป็นของแถวไหน **ให้ล้มเสียงดัง**
            raise o
        g, sub, status = o
        cls = _classify(status)
        if cls == "ok":
            ok_sub_ids.add(sub["id"])
        elif cls == "gone":
            # ☠️ ปลายทางตายแล้ว ⇒ **ต้องเก็บ id ไว้ลบ** (ไม่ใช่แค่ปล่อยผ่าน)
            #    🚨 เคยพลาดตรงนี้จริง (28 ก.ย. 2026): เขียนเป็น `elif cls != "gone"` แล้ว
            #       ลืมสาขา `gone` ⇒ `dead_sub_ids` ว่างตลอดกาล ⇒ `stats["gone"] = 0`
            #       และ **ไม่มีใครถูกลบเลย** ⇒ ปลายทางที่ตายถูกยิงซ้ำทุกครั้งที่มี
            #       notification ใหม่ ตลอดไป · อาการภายนอกดูปกติทุกอย่าง (ไม่มี error
            #       มีแค่ log 410 มากขึ้นเรื่อย ๆ) — T9 จับได้เพราะมัน assert `stats["gone"]`
            #       ⚠️ บทเรียน: เวลาเติมสาขาให้ `if` ให้ **คงสาขาเดิมไว้ครบ** แล้วค่อยเพิ่ม
            #          อย่าเขียนเงื่อนไขใหม่ทับ (การรวบเป็น `!=` ทำให้สาขาหายโดยไม่รู้ตัว)
            dead_sub_ids.add(sub["id"])
        else:
            # `retry` / `permanent` — ปลายทางยังอยู่ แต่รอบนี้ไม่ผ่าน ⇒ จดไว้ว่ามันล้ม
            # (ต่างจาก `gone` ที่แถวจะถูกลบทั้งแถว นับไปก็ไม่มีใครดู)
            failed_sub_ids.add(sub["id"])
        results.append({"outbox_id": g["meta"]["outbox_id"], "cls": cls, "status": status})

    # ==================== จดผล (tx ใหม่) ====================
    # 📌 **ไม่มี `if r["outbox_id"] is None: continue` ที่นี่โดยเจตนา** — บรรทัดนั้นเคยอยู่
    #    และมันคือครึ่งหลังของรูข้างบน: รับ "retry" ที่ไม่มีเจ้าของเข้ามา แล้ว **ทิ้งเงียบ ๆ**
    #    ⇒ ทุกผลลัพธ์ที่มาถึงจุดนี้ต้องมีเจ้าของเสมอ (`one()` รับประกัน) ถ้าไม่มี = โค้ดผิด
    per_outbox: Dict[int, List[str]] = {}
    for r in results:
        per_outbox.setdefault(r["outbox_id"], []).append(r["cls"])

    done_ids: List[int] = []
    retry_ids: List[int] = []
    for oid, classes in per_outbox.items():
        if "ok" in classes:
            # นโยบาย "สำเร็จอย่างน้อย 1 เครื่อง = จบ" (ดู docstring)
            done_ids.append(oid)
            stats["sent"] += 1
        elif all(c == "gone" for c in classes):
            # ทุกอุปกรณ์ตายแล้ว — ไม่มีอะไรให้ retry
            done_ids.append(oid)
        elif any(c == "retry" for c in classes):
            retry_ids.append(oid)
        else:
            # permanent ล้วน (400 อื่น ๆ) — ยิงซ้ำอีก 100 ครั้งก็ได้เรื่องเดิม
            done_ids.append(oid)

    if dead_sub_ids:
        # ⚠️ ลบ subscription ที่ตาย **ก่อน** ปิด outbox — ถ้าลบไม่สำเร็จแล้วปิดไปแล้ว
        #    ปลายทางที่ตายจะถูกยิงซ้ำทุกครั้งที่มี notification ใหม่
        removed = await delete_subscriptions_by_id(pool, list(dead_sub_ids))
        stats["gone"] = removed
        logger.info("🧹 ลบปลายทางที่ตายแล้ว %d รายการ (HTTP 404/410)", removed)

    # 📊 อัปเดตสุขภาพปลายทาง — ข้ามแถวที่ถูกลบไปแล้ว (dead) ไม่งั้น UPDATE ไปโดนศูนย์แถว
    await _mark_subscription_health(
        pool,
        ok_ids=sorted(ok_sub_ids - dead_sub_ids),
        failed_ids=sorted(failed_sub_ids - dead_sub_ids),
    )

    await _finish(pool, done_ids)
    if retry_ids:
        rescheduled, exhausted = await _retry_later(pool, retry_ids, error="send-failed")
        stats["retry"] = rescheduled
        # 🗑️ "ยอมแพ้แล้ว" — push ที่ลองครบเพดานแล้วยังไม่ผ่าน = **หายถาวร**
        #    ต้องมีตัวนับนี้แยกจาก `retry` ไม่งั้นของที่หายไปจะไม่มีใครเห็น
        stats["dropped"] = exhausted
        if rescheduled:
            logger.warning("🔁 เลื่อนส่ง %d รายการไปรอบหน้า", rescheduled)
        if exhausted:
            logger.error(
                "🗑️ ยอมแพ้ %d รายการ — ลองครบ %d ครั้งแล้วยังไม่ผ่าน (push หายถาวร)",
                exhausted, settings.PUSH_MAX_ATTEMPTS,
            )

    return stats


async def drain(pool, *, sender=None,
                deadline_seconds: Optional[float] = None) -> Dict[str, int]:
    """ระบายคิวจนว่าง หรือจนหมดงบเวลา — **อัตราส่งไม่ขึ้นกับความถี่ของคนเรียก**

    ⭐ **ทำไมต้องมีทั้งที่ `process_pending` ทำงานได้อยู่แล้ว**
       `process_pending` ทำได้แค่ "1 batch ต่อ 1 รอบ" ⇒ throughput =
       `PUSH_BATCH_SIZE × ความถี่ของ cron` ซึ่งพังทันทีที่ cron ไม่มาตามนัด
       (วัดจาก staging 28 ก.ย. 2026: cron ที่ออกแบบไว้ทุก 20 วิ ยิงจริงทุก ~150 วิ
        ⇒ 733 แถวที่ควรระบายใน 3 นาที ใช้เวลา 40 นาที ของจริงจึงหมดอายุและถูกทิ้ง)

       `drain` ตัดความเชื่อมโยงนั้นออก: **คนเรียกถี่แค่ไหน คิวก็ระบายจนเกลี้ยงเท่านั้น**
       ⇒ cron จะยิง 20 วิ หรือ 150 วิ ก็ไม่เปลี่ยนเวลาที่ push ถึงมือ (เหลือแค่ "เริ่มช้า
       ได้ไม่เกิน 1 tick" ซึ่งเป็นหน้าที่ของ `PUSH_TICK_SECONDS` ไม่ใช่ของฟังก์ชันนี้)

    ⚠️ **งบเวลาจำเป็น ไม่ใช่ของประดับ** — `job_timeout = 120` ของ ARQ จะตัดงานทิ้ง
       กลางคันถ้าเกิน และแถวที่ claim ไว้จะค้างจนกว่าจะถึงรอบกู้ (`PUSH_RECOVER_MINUTES`)
       ⇒ ต้องหยุดเองก่อนเสมอ (ค่าเริ่มต้น 45 วิ เหลือ margin 2.6 เท่า)

    ⚠️ **ไม่ loop เปล่าเมื่อคิวว่าง** — ออกทันทีที่ `claimed == 0` ไม่ต้องรอครบงบ
       (รอบปกติของระบบที่มีแค่คนมีอุปกรณ์ = 1 คิวรีแล้วจบ ⇒ จ่ายถูกพอจะเรียกทุก 5 วิ)

    `sender` = injectable ส่งต่อให้ `process_pending` (เทสต์ไม่ต้องออกเน็ต)
    """
    budget = settings.PUSH_DRAIN_SECONDS if deadline_seconds is None else deadline_seconds
    deadline = time.monotonic() + budget
    total = {"claimed": 0, "sent": 0, "gone": 0, "retry": 0,
             "dropped": 0, "skipped": 0, "stale": 0, "quiet": 0}

    while True:
        stats = await process_pending(pool, sender=sender)
        # ⚠️ **วนจาก `stats` ไม่ใช่จาก `total`** — ตัวนับที่ `process_pending` เพิ่มใหม่
        #    จะไหลมารวมเองโดยไม่ต้องแก้ที่นี่ และไม่เกิด `KeyError` เงียบ ๆ
        #    (ถ้าวนจาก `total` ตัวนับใหม่จะถูกทิ้งทุก batch = หายจาก log ทั้งที่ทำงานจริง)
        #    · แต่ `_log_stats` ฝั่ง worker ยัง **ลิสต์ชื่อคีย์ตรง ๆ โดยเจตนา** ⇒ ตัวนับใหม่
        #    ที่ไม่มีในบรรทัด log จะพังเสียงดังตอน `claimed > 0` ไม่ใช่หายเงียบ
        #    (บทเรียน §20.18 สาเหตุ #4: ตัวนับที่ไม่มีใครเห็น = ปัญหาที่มองไม่เห็นเป็นวัน)
        for k, v in stats.items():
            total[k] = total.get(k, 0) + v
        # คิวว่าง = งานหมดแล้ว ออกทันที (ไม่กินงบที่เหลือ)
        if stats["claimed"] == 0:
            break
        # ยังมีของค้างอยู่แต่หมดเวลา ⇒ ออกรอบถัดไปทำต่อ (ไม่ปล่อยให้ job ถูกตัดกลางคัน)
        if time.monotonic() >= deadline:
            logger.warning(
                "⏳ ระบายคิวไม่ทันใน %.0f วิ — หยุดเพื่อไม่ให้เกิน job_timeout "
                "(รอบถัดไปทำต่อ · ถ้าเห็นบ่อยแปลว่าคิวโตเกินกำลัง)",
                budget,
            )
            break

    return total


async def recover_stale_outbox(pool) -> int:
    """กู้แถวที่ถูก claim ค้างไว้ (worker ตายกลางคันหลัง claim ก่อนจดผล)

    ⚠️ ถ้าไม่มีด่านนี้ แถวที่ `processing_at` ค้างจะ **ไม่มีวันถูกหยิบอีกเลย**
       (คิวรี claim กรอง `processing_at IS NULL`) ⇒ push หยุดเงียบ ๆ ไม่มี error
       — เป็นอาการที่หาสาเหตุยากที่สุดในระบบคิว

    🚨 **`PUSH_RECOVER_MINUTES` ต้องน้อยกว่า `PUSH_MAX_AGE_MINUTES` — ไม่ใช่ใช้ค่า
       เดียวกัน** (ผมเขียนเวอร์ชันแรกโดยใช้ `PUSH_MAX_AGE_MINUTES` ด้วย และเทสต์ T13
       จับได้): ถ้าเกณฑ์กู้เท่ากับเกณฑ์ stale แถวที่กู้คืนมาจะ **ถูก mark stale ทันที
       ในรอบเดียวกัน** ⇒ ด่านนี้กลายเป็นพิธีกรรมที่ไม่เคยกู้ push อะไรได้จริงเลย
       (ดูดแค่แถวให้คิวไม่ค้าง) — ต้องกู้ให้เร็วพอที่ push ยังมีอายุเหลือ

    เกณฑ์ 5 นาทีมาจาก `job_timeout = 120` วินาทีของ worker ⇒ แถวที่ค้างเกิน 5 นาที
    คือ "ตายแน่นอน" (2.5 เท่าของเวลาที่งานมีสิทธิ์กิน) ไม่ใช่ "ยังทำงานอยู่"
    """
    minutes = max(settings.PUSH_RECOVER_MINUTES, 1)
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE push_outbox
               SET processing_at = NULL
             WHERE processed_at IS NULL
               AND processing_at IS NOT NULL
               AND processing_at < NOW() - ($1 * INTERVAL '1 minute')
            """,
            minutes,
        )
    return int(result.split()[-1])


async def cleanup_outbox(pool, days: Optional[int] = None) -> int:
    """ลบแถวที่จบแล้วและเก่ากว่า N วัน

    ⚠️ **ตัวที่กันของค้างไว้จริง ๆ คือ `processed_at < …`** — แถวที่ยังไม่ส่งมี
       `processed_at IS NULL` ⇒ `NULL < timestamp` = `NULL` ⇒ ไม่เข้าเงื่อนไข
       (พิสูจน์ด้วย mutation แล้ว: ลบ `processed_at IS NOT NULL` ออก เทสต์ T14 ยังผ่าน)
       ⇒ บรรทัด `processed_at IS NOT NULL` เก็บไว้เป็น **เอกสารเจตนา + เกราะกันการ
       แก้ในอนาคต** (เช่นมีคนเปลี่ยนไปใช้ `COALESCE(processed_at, created_at)`)
       ไม่ใช่ด่านหลัก — **อย่าลบเงื่อนไข `processed_at <` ออกเด็ดขาด** (T14 จับ)
    """
    d = settings.PUSH_RETENTION_DAYS if days is None else days
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM push_outbox
             WHERE processed_at IS NOT NULL
               AND processed_at < NOW() - ($1 * INTERVAL '1 day')
            """,
            d,
        )
    return int(result.split()[-1])
