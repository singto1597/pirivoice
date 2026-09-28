"""สร้าง VAPID key pair สำหรับ Web Push (A3)

วิธีรัน (ต้องมี Docker เพราะ `py-vapid` ไม่ได้ติดตั้งบนเครื่อง host):
    docker compose -f docker-compose.test.yml run --rm test_runner \
        python /app/scripts/generate_vapid_keys.py

ผลลัพธ์ = 3 บรรทัด `KEY=value` พร้อมคัดลอกลง `.env` ของ **ทั้งสอง clone** บน VPS:
    ~/prsc_portal/prsc_test/.env   (staging)
    ~/prsc_portal/piri_voice/.env  (production)

⚠️ **ห้าม commit private key** — `.env` gitignored อยู่แล้ว ไฟล์นี้พิมพ์ออกจอเท่านั้น
⚠️ **rotate key = subscription เดิมใช้ไม่ได้ทั้งหมด** ⇒ ต้องลบแถวใน `push_subscriptions`
   แล้วให้นักเรียนกด "เปิดการแจ้งเตือน" ใหม่ทุกคน (เบราว์เซอร์ผูก subscription กับ public key
   ตั้งแต่ตอน subscribe) — ดูคอมเมนต์ใน `core/config.py`

────────────────────────────────────────────────────────────────
ทำไมเก็บเป็น **base64url บรรทัดเดียว** ไม่ใช่ PEM
────────────────────────────────────────────────────────────────
ค่าเหล่านี้ต้องอยู่ใน `.env` ซึ่งเป็น key=value บรรทัดเดียว — PEM หลายบรรทัดจะต้อง
แปลง `\n` เป็น literal ซึ่งอ่านยากและพิมพ์ผิดง่าย
`py_vapid.Vapid02.from_string()` **รองรับรูปนี้อยู่แล้ว**: มัน strip whitespace →
base64url-decode → ถ้าได้ 32 byte จะเดินเส้น `from_raw()` (สเกลาร์ล้วน) ตรง ๆ
⇒ ไม่ต้องมี header `-----BEGIN…` เลย

────────────────────────────────────────────────────────────────
⭐ สคริปต์นี้ **ตรวจของที่สร้างก่อนพิมพ์** (ไม่ใช่แค่ generate แล้วหวัง)
────────────────────────────────────────────────────────────────
สคริปต์ dev ที่พิมพ์ค่าผิดจะพาไปสู่การดีบักที่แพงมาก (push ไม่ขึ้นโดยไม่มี error)
⇒ ทดสอบ 3 อย่างก่อนพิมพ์ แล้ว `return 1` ถ้าข้อใดไม่ผ่าน:
  1. `Vapid02.from_string(private_b64)` อ่านกลับได้และได้สเกลาร์เดิม
  2. public ที่ encode ไว้ = public ที่ derive จาก private ที่อ่านกลับ (คู่กันจริง)
  3. ยิง JWT จริงด้วย `sign()` แล้ว decode payload ออกมา + `aud` ตรง
     (ถ้า `sub`/`aud` ผิดรูปแบบ py-vapid จะ raise **ที่นี่** ไม่ใช่ตอนผู้ใช้กดเปิด push)
"""
import base64
import json
import sys
import time

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid02


def _b64url(raw: bytes) -> str:
    """base64url **ไม่มี padding** — รูปเดียวกับที่เบราว์เซอร์ส่ง `applicationServerKey` กลับมา"""
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _raw_public(key) -> bytes:
    """public key → uncompressed point 65 byte (0x04 ‖ X ‖ Y)"""
    return key.public_bytes(encoding=Encoding.X962, format=PublicFormat.UncompressedPoint)


def _decode_jwt_part(part: str) -> dict:
    """ถอด payload ของ JWT โดยไม่ตรวจ signature (เราสร้างเอง จึงเชื่อได้)"""
    return json.loads(base64.urlsafe_b64decode(part + "==="))


def main() -> int:
    vapid = Vapid02()
    vapid.generate_keys()

    # private = สเกลาร์ 32 byte (big-endian)
    private_b64 = _b64url(
        vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    )
    # ⭐ public = ค่าที่เบราว์เซอร์ต้องการเป็น `applicationServerKey` ตรง ๆ
    #    ส่งเป็น **สตริง** ไม่ได้ — ฝั่ง frontend ต้องแปลงเป็น Uint8Array ก่อน
    #    (Chrome throw ทันที / **Safari เงียบ** — ดูกับดักข้อ 2 ใน push.ts)
    public_b64 = _b64url(_raw_public(vapid.public_key))

    # ================= ตรวจ 1: อ่าน private กลับได้ =================
    try:
        round_trip = Vapid02.from_string(private_b64)
        restored = round_trip.private_key.private_numbers().private_value
    except Exception as e:  # pragma: no cover — เกิดเฉพาะตอน py-vapid เปลี่ยน API
        print(f"❌ อ่าน private key กลับด้วย Vapid02.from_string() ไม่ได้: {e}", file=sys.stderr)
        print("   ⇒ .env ที่ได้จะใช้ไม่ได้ — อย่านำไปใส่", file=sys.stderr)
        return 1
    if vapid.private_key.private_numbers().private_value != restored:
        print("❌ private key ที่อ่านกลับไม่ตรงกับตัวที่สร้าง", file=sys.stderr)
        return 1

    # ================= ตรวจ 2: public ตรงกับ private =================
    if _b64url(_raw_public(round_trip.private_key.public_key())) != public_b64:
        print("❌ public key ไม่ตรงกับ private key ที่สร้าง", file=sys.stderr)
        return 1

    # ================= ตรวจ 3: ยิง JWT จริง =================
    # ใช้ `aud` ปลอมแบบ FCM — พิสูจน์ว่า `sign()` ทำงานกับคีย์รูปนี้จริง
    # และพิสูจน์ว่ารูปแบบ `sub`/`aud` ที่เราจะใช้ผ่าน validator ของ py-vapid
    try:
        headers = round_trip.sign(
            {
                "sub": "mailto:admin@example.com",
                "aud": "https://fcm.googleapis.com",
                "exp": int(time.time()) + 60,
            }
        )
    except Exception as e:
        print(f"❌ ทดสอบ sign() ไม่ผ่าน: {e}", file=sys.stderr)
        return 1

    auth = headers.get("Authorization", "")
    if not auth.startswith("vapid t="):
        print(f"❌ รูปแบบ Authorization header ไม่ใช่ RFC 8292: {auth[:60]}", file=sys.stderr)
        return 1
    # `vapid t=<jwt>,k=<pubkey>` — เอาแค่ jwt
    jwt = auth[len("vapid t="):].split(",")[0]
    parts = jwt.split(".")
    if len(parts) != 3:
        print(f"❌ JWT ไม่มี 3 ส่วน: {len(parts)}", file=sys.stderr)
        return 1
    payload = _decode_jwt_part(parts[1])
    if payload.get("aud") != "https://fcm.googleapis.com":
        print(f"❌ `aud` ใน JWT ไม่ตรง: {payload.get('aud')}", file=sys.stderr)
        return 1

    # ================= ผ่านทุกด่าน — พิมพ์ =================
    print()
    print("=" * 72)
    print("✅ ตรวจผ่านทั้ง 3 ด่าน (round-trip · public↔private · JWT sign)")
    print("=" * 72)
    print("คัดลอก 3 บรรทัดนี้ไปต่อท้าย .env ของ **ทั้งสอง clone** บน VPS:")
    print()
    print(f"VAPID_PUBLIC_KEY={public_b64}")
    print(f"VAPID_PRIVATE_KEY={private_b64}")
    print("VAPID_SUBJECT=mailto:<อีเมลจริงของสภา>")
    print()
    print("⚠️  VAPID_SUBJECT ต้องขึ้นต้นด้วย mailto: เท่านั้น (RFC 8292)")
    print("⚠️  อย่า commit ค่าสองบรรทัดแรก · .env gitignored อยู่แล้ว")
    print("⚠️  ใช้ key ชุดเดียวกันทั้งสอง clone ได้ แต่แยกกันจะ rotate ฝั่งใดฝั่งหนึ่ง")
    print("    ได้อิสระต่อกัน (แนะนำสำหรับ production)")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
