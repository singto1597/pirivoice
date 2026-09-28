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
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import http_ece
import httpx
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid02

from core.config import settings

logger = logging.getLogger("PUSH")

# ปลายทางเริ่มต้นของ notification — A4 (deep link) จะมาเปลี่ยนให้ตรงเรื่อง/บอร์ด
# ⚠️ ต้องเป็น `/app/notifications` **ไม่ใช่** `/notifications` — router ของ frontend
#    มี redirect แบบ string ที่ทำ query หลุด (ดูกับดักในแผน §20.8)
DEFAULT_PUSH_URL = "/app/notifications"

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

def build_payload(row: Any) -> Dict[str, Any]:
    """สร้าง payload ของ notification 1 อัน — **ฟังก์ชันบริสุทธิ์**

    แยกออกมาเป็น pure function โดยเจตนา: รูป payload คือสัญญาระหว่าง backend กับ
    `sw.js` (ซึ่งอ่าน `event.data.json()`) ⇒ ถ้าที่นี่เปลี่ยนชื่อคีย์ `sw.js` จะพัง
    โดยไม่มีอะไรจับได้ในฝั่ง Python · การเป็น pure function ทำให้เทสต์ยิงตรงได้

    คีย์ที่ `sw.js` อ่านจริง (ดู `frontend/public/sw.js`):
      - `title`, `body` → เนื้อ notification
      - `tag`           → ให้ notification ใหม่ *แทนที่* อันเก่าของเรื่องเดียวกัน
                          (ไม่ให้มือถือขึ้นซ้ำ 5 อันเมื่อมีคนตอบรัว ๆ)
      - `data.url`      → ปลายทางเมื่อคลิก
    """
    return {
        "title": row["title"],
        "body": row["body"],
        "tag": f"piri-notif-{row['notification_id']}",
        "data": {
            "url": DEFAULT_PUSH_URL,
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
                   n.entity_type, n.entity_id, n.board_id,
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
             "dropped": 0, "skipped": 0, "stale": 0}

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

    if not to_send:
        return stats

    # ==================== ยิง HTTP — ไม่ถือ DB connection ====================
    sem = asyncio.Semaphore(settings.PUSH_SEND_CONCURRENCY)
    ttl = settings.PUSH_TTL_SECONDS
    results: List[Dict[str, Any]] = []
    dead_sub_ids: set = set()

    async with httpx.AsyncClient(timeout=_SEND_TIMEOUT_SECONDS) as client:
        send = sender or _send_one

        async def one(g: Dict[str, Any], sub: Dict[str, Any], payload: Dict[str, Any]):
            async with sem:
                status = await send(client, sub, payload, ttl=ttl)
            return g, sub, status

        tasks = [
            one(g, sub, build_payload(g["meta"]))
            for g in to_send for sub in g["subs"]
        ]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    for o in outcomes:
        if isinstance(o, BaseException):
            # ข้อผิดพลาดที่หลุดจาก _send_one (ไม่ควรเกิด เพราะมัน catch ไว้แล้ว)
            # — นับเป็น retryable ไม่ให้ทั้งรอบล้ม
            logger.exception("❌ sender โยน exception", exc_info=o)
            results.append({"outbox_id": None, "cls": "retry"})
            continue
        g, sub, status = o
        cls = _classify(status)
        if cls == "gone":
            dead_sub_ids.add(sub["id"])
        results.append({"outbox_id": g["meta"]["outbox_id"], "cls": cls, "status": status})

    # ==================== จดผล (tx ใหม่) ====================
    per_outbox: Dict[int, List[str]] = {}
    for r in results:
        if r["outbox_id"] is None:
            continue
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
