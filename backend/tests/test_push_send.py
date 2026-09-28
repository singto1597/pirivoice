"""
🌐 เส้นทางส่ง push จริง — VAPID + ECE round-trip (A3)
======================================================
⚠️ **ช่องที่ไฟล์นี้ปิด:** `test_push_outbox.py` แทน sender ด้วยของปลอม **ทุกตัว**
   (`sender=` injectable) ⇒ `_send_one()` ไม่เคยถูกเรียกจริงแม้แต่ครั้งเดียว
   ⇒ VAPID signing, ECE encryption และการ decode กุญแจ **ไม่มีการทดสอบเลย**

ทำไมต้องมีไฟล์นี้: `_send_one()` คือโค้ดที่ **"ผิดแล้วเงียบที่สุด"** ในงานนี้ —
ถ้า `dh`/`auth_secret` ส่งผิดรูป (สตริง base64url แทน bytes) หรือ `aud` ไม่ตรง
ผู้ให้บริการจะตอบ 400/401 แล้ว push จะไม่ถึงมือใคร **โดยที่ฝั่งเรามองไม่เห็นเลย**
เพราะ worker ไม่มีใครอ่าน response ⇒ ต้องพิสูจน์ด้วยการ **ถอดรหัส body ที่ส่งจริงกลับ**

วิธีทดสอบ: เปิด HTTP server ในเครื่อง (127.0.0.1, พอร์ตว่าง) รับ request แล้ว
**ถอดรหัสด้วยกุญแจฝั่ง "เบราว์เซอร์"** ⇒ เทสต์ไม่ออกเน็ตเลย แต่พิสูจน์ครบทั้งวงจร

⚠️ **ขอบเขตที่ไฟล์นี้พิสูจน์ไม่ได้ (พูดตรง ๆ):** ใช้ `http://` ไม่ใช่ `https://`
   เพราะจะขอ cert ที่เชื่อถือได้ให้ listener ชั่วคราวไม่ได้ · แต่สิ่งที่ต้องพิสูจน์
   จาก `https` คือ **`aud`** ซึ่งเทสต์นี้ assert ตรง ๆ ว่า `aud` = origin ของ endpoint
   ที่ยิงไปจริง **รวม port** (ถ้ามีคน hardcode `https://fcm.googleapis.com` หรือ
   ตัด port ทิ้ง เทสต์จะจับได้ทันที) · ส่วน TLS เองเป็นหน้าที่ของ `httpx`
"""
import base64
import importlib.util
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import http_ece
import httpx
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from jose import jwt as jose_jwt
from py_vapid import Vapid02

from core.config import settings
from services import push_service

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "generate_vapid_keys.py"


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def vapid_real_keys(monkeypatch):
    """คีย์ VAPID **จริง** (P-256) ไม่ใช่สตริงปลอม

    ⭐ ใช้ helper จาก `scripts/generate_vapid_keys.py` โดยตรง (โหลดผ่าน importlib)
       ⇒ เทสต์ไฟล์นี้ **ตรวจรูปแบบคีย์ที่สคริปต์นั้นจะเขียนลง `.env` ไปด้วย**
       ถ้าสคริปต์เปลี่ยนไปสร้างรูปที่ `from_string` อ่านไม่ได้ push ทั้งระบบจะตาย
       ตอน deploy — และนั่นคือความผิดพลาดที่แพงที่สุดของงานนี้

    ⚠️ `Vapid02.sign()` **validate** `sub` (ต้อง mailto:/URL) และ `aud`
       (regex `^https?://[^/:]+(:\\d+)?$` — ห้ามมี path) ⇒ ตั้งค่าที่ถูกต้องที่นี่
    """
    spec = importlib.util.spec_from_file_location("gen_vapid", SCRIPT)
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)

    key = Vapid02()
    key.generate_keys()
    private_b64 = gen._b64url(
        key.private_key.private_numbers().private_value.to_bytes(32, "big")
    )
    public_b64 = gen._b64url(gen._raw_public(key.public_key))

    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", public_b64)
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", private_b64)
    monkeypatch.setattr(settings, "VAPID_SUBJECT", "mailto:council@piriyalai.ac.th")
    push_service._reset_vapid_cache()
    yield {"private_b64": private_b64, "public_b64": public_b64, "key": key}
    push_service._reset_vapid_cache()


@pytest.fixture
def browser():
    """กุญแจฝั่ง "เบราว์เซอร์" — ตัวที่ `pushManager.subscribe()` จะสร้างให้

    คืนทั้งรูป base64url (ที่เก็บลง DB) และตัว object จริง (ที่ใช้ถอดรหัส)
    """
    priv = ec.generate_private_key(ec.SECP256R1())
    raw_auth = os.urandom(16)
    return {
        "priv": priv,
        "raw_auth": raw_auth,
        # เบราว์เซอร์ส่ง base64url **ไม่มี padding** — `_decode_key` ต้องรับรูปนี้ได้
        "p256dh": base64.urlsafe_b64encode(
            priv.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        ).decode().rstrip("="),
        "auth": base64.urlsafe_b64encode(raw_auth).decode().rstrip("="),
    }


class _PushServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.captured: list[dict] = []
        self.status = 201


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 — ชื่อที่ BaseHTTPRequestHandler กำหนด
        length = int(self.headers.get("Content-Length") or 0)
        self.server.captured.append({
            "path": self.path,
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": self.rfile.read(length),
        })
        self.send_response(self.server.status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):  # ปิด log รบกวน output ของ pytest
        pass


@pytest.fixture
def push_server():
    """HTTP server ในเครื่อง — **จำลอง 'ผู้ให้บริการ push'** (ไม่มีเน็ตออกนอก)"""
    srv = _PushServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def _endpoint(srv, path="/push/device-1") -> str:
    return f"http://127.0.0.1:{srv.server_address[1]}{path}"


def _subscription(endpoint, browser) -> dict:
    """รูปเดียวกับที่ `_load_payloads()` คืนมา (คีย์ต้องตรงกันเป๊ะ)"""
    return {"id": 1, "endpoint": endpoint,
            "p256dh": browser["p256dh"], "auth": browser["auth"]}


def _payload() -> dict:
    """payload จริงจาก `build_payload()` — ผูกสัญญาระหว่าง backend กับ `sw.js`"""
    return push_service.build_payload({
        "notification_id": 42, "title": "มีเรื่องใหม่", "body": "ทดสอบ ✓ อักษรไทย",
        "type": "issue_new", "entity_type": "issue", "entity_id": 7, "board_id": None,
    })


def _vapid_token(auth_header: str) -> str:
    """`vapid t=<jwt>,k=<key>` → `<jwt>` (RFC 8292)"""
    assert auth_header.startswith("vapid t="), f"ไม่ใช่รูป RFC 8292: {auth_header[:40]}"
    return auth_header[len("vapid t="):].split(",")[0]


def _ece_keyid(body: bytes) -> bytes:
    """อ่าน ephemeral public key ของผู้ส่งจาก header ของ body (RFC 8188 §2.1)"""
    id_len = body[20]
    return body[21:21 + id_len]


# ============================================================
# 1) ยิงจริง → ได้ status + header ถูกต้อง
# ============================================================

@pytest.mark.asyncio
async def test_E1_real_send_returns_status_and_rfc8292_headers(push_server, browser, vapid_real_keys):
    """`_send_one()` ยิงจริง → คืน status ของผู้ให้บริการ + header ครบตาม RFC

    ⚠️ `k=` ใน Authorization **ต้องเท่ากับ VAPID public key ของเรา** — ถ้าส่งค่า
       อื่น (หรือ encode ผิดรูป) ผู้ให้บริการจะปฏิเสธ JWT ทุกอัน

    mutation ที่ต้องทำให้แตก: ลบ `headers.update({...})` → ไม่มี Content-Encoding
    """
    sub = _subscription(_endpoint(push_server), browser)
    async with httpx.AsyncClient(timeout=10) as client:
        status = await push_service._send_one(client, sub, _payload(), ttl=3600)

    assert status == 201
    assert len(push_server.captured) == 1
    sent = push_server.captured[0]

    assert sent["path"] == "/push/device-1"
    assert sent["headers"]["content-encoding"] == "aes128gcm"
    assert sent["headers"]["ttl"] == "3600"
    # ★ `Urgency` **ต้องมีจริง** — ถ้าลบ `"Urgency": _urgency()` ออกจาก `headers.update({...})`
    #   header นี้จะหาย ⇒ FCM กลับไปใช้ `normal` = เลื่อนการส่งจนกว่าเครื่องจะตื่น
    #   ⇒ อาการจริงที่เจอ: "ปิดแอพอยู่ไม่เด้ง พอเปิดแอพเด้งมาทั้งกองเก่า"
    assert sent["headers"]["urgency"] == "high"
    # ⚠️ **ห้ามมี Content-Type** — pywebpush ก็ไม่ส่ง (ดูคอมเมนต์ใน `_send_one`)
    assert "content-type" not in sent["headers"]

    auth = sent["headers"]["authorization"]
    assert f",k={vapid_real_keys['public_b64']}" in auth, "k= ต้องเป็น public key ของเรา"


@pytest.mark.asyncio
async def test_E2_vapid_jwt_signature_verifies_and_aud_is_endpoint_origin(
    push_server, browser, vapid_real_keys
):
    """★ ลายเซ็น VAPID JWT ตรวจได้ด้วย public key ของเรา + claims ถูกต้อง

    ⭐ **`aud` ต้องเป็น origin ของ endpoint ที่ยิงไปจริง — รวม port**
       `_base_sign()` ของ py-vapid ตรวจ `aud` ด้วย regex `^https?://[^/:]+(:\\d+)?$`
       (ห้ามมี path) ⇒ ถ้าใครเปลี่ยนไปใช้ `f"{scheme}://{host}"` (ตัด port) หรือ
       hardcode `https://fcm.googleapis.com` **ผู้ให้บริการจะปฏิเสธทุก push**
       และเราจะไม่เห็น error นั้นเลย — เทสต์นี้คือด่านเดียวที่จับได้

    mutation ที่ต้องทำให้แตก: `aud` = `"https://fcm.googleapis.com"` ตายตัว →
        เทสต์ล้ม · `aud` = `u.netloc` (ไม่มี scheme) → py-vapid raise
    """
    sub = _subscription(_endpoint(push_server), browser)
    expected_aud = f"http://127.0.0.1:{push_server.server_address[1]}"

    async with httpx.AsyncClient(timeout=10) as client:
        await push_service._send_one(client, sub, _payload(), ttl=60)

    token = _vapid_token(push_server.captured[0]["headers"]["authorization"])

    # ลายเซ็น ES256 ตรวจด้วย public key ที่ derive จากคีย์ที่เราตั้งไว้
    pem = vapid_real_keys["key"].public_key.public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    claims = jose_jwt.decode(
        token, pem, algorithms=["ES256"],
        audience=expected_aud,          # ← jose ตรวจ `aud` ให้เองในตัว
    )
    assert claims["sub"] == settings.VAPID_SUBJECT
    assert claims["sub"].startswith("mailto:"), "RFC 8292 บังคับ mailto:"
    assert claims["exp"] > time.time() + 3600, "อายุควรยาวพอให้ retry ได้หลายรอบ"


@pytest.mark.asyncio
async def test_E3_ece_body_decrypts_back_to_exact_payload(push_server, browser):
    """★★★ หัวใจของไฟล์นี้: **ถอดรหัส body ที่ส่งจริงกลับได้ payload เดิมเป๊ะ**

    พิสูจน์พร้อมกัน 4 อย่างที่ผิดแล้วเงียบ:
      1. `dh`/`auth_secret` ถูก decode จาก base64url เป็น **bytes** (ถ้าส่งสตริง
         ตรง ๆ ผู้ให้บริการจะได้ body ที่ถอดไม่ได้ — และเราจะไม่รู้เลย)
      2. `version="aes128gcm"` + header block (salt ‖ rs ‖ idlen ‖ keyid) ถูกต้อง
      3. ข้อความไทย/อีโมจิไม่เพี้ยน (`ensure_ascii=False` → UTF-8)
      4. รูป payload ตรงกับที่ `sw.js` จะอ่าน (`title`/`body`/`tag`/`data.url`)

    ⚠️ **นี่คือเทสต์เดียวในโปรเจคที่พิสูจน์ว่าการเข้ารหัสถูกต้อง** — ถอดด้วยกุญแจ
       ฝั่งเบราว์เซอร์ (แบบที่เบราว์เซอร์จะทำจริง) ไม่ใช่ถอดด้วยกุญแจของเราเอง
       (ซึ่งจะผ่านเสมอแม้เข้ารหัสผิดวิธี)

    mutation ที่ต้องทำให้แตก: สลับ `dh`/`auth_secret` · ตัด `.rstrip("=")` handling
        ใน `_decode_key` · เปลี่ยน version เป็น `"aesgcm"` · ลบ `ensure_ascii=False`
    """
    payload = _payload()
    sub = _subscription(_endpoint(push_server), browser)

    async with httpx.AsyncClient(timeout=10) as client:
        await push_service._send_one(client, sub, payload, ttl=60)

    body = push_server.captured[0]["body"]
    plaintext = http_ece.decrypt(
        body,
        private_key=browser["priv"],       # ← กุญแจฝั่งเบราว์เซอร์
        auth_secret=browser["raw_auth"],   # ← รูป bytes (ไม่ใช่ base64url)
        version="aes128gcm",
        # `dh` ไม่ต้องส่ง: aes128gcm ฝัง public key ของผู้ส่งไว้ใน header ของ body
        # (`decrypt()` จะดึงจาก keyid เอง) — และการไม่ส่งคือการพิสูจน์ว่า header ถูกต้อง
    )

    assert json.loads(plaintext) == payload, "payload ที่ถอดได้ไม่ตรงกับที่ส่ง"


@pytest.mark.asyncio
async def test_E4_ephemeral_key_is_fresh_per_message(push_server, browser):
    """★ ephemeral key ต้อง **ใหม่ทุกข้อความ** (RFC 8291 บังคับ)

    ถ้า cache/reuse กุญแจชั่วคราว: กุญแจ AES จะซ้ำเมื่อส่งให้อุปกรณ์เดิม ⇒
    ผู้ดักฟังที่เก็บ push หลายอันเทียบกันจะเรียนรู้ความสัมพันธ์ได้

    ⚠️ `salt` ที่สุ่มใหม่ทุกครั้งทำให้ body ต่างกันอยู่แล้ว ⇒ เทสต์นี้ **ไม่ดู body**
       แต่ดู `keyid` ใน header ซึ่งเป็น ephemeral public key โดยตรง — จุดที่
       การ reuse จะปรากฏจริง (ถ้าดูแค่ body ที่ต่างกันจะผ่านทั้งที่ reuse key)

    mutation ที่ต้องทำให้แตก: ย้าย `ec.generate_private_key(...)` ออกไปเป็น
        module-level constant → keyid ซ้ำทั้งสองครั้ง
    """
    sub = _subscription(_endpoint(push_server), browser)
    async with httpx.AsyncClient(timeout=10) as client:
        await push_service._send_one(client, sub, _payload(), ttl=60)
        await push_service._send_one(client, sub, _payload(), ttl=60)

    assert len(push_server.captured) == 2
    keys = [_ece_keyid(c["body"]) for c in push_server.captured]

    assert all(len(k) == 65 for k in keys), "ephemeral public key ต้องเป็น uncompressed point 65 byte"
    assert keys[0] != keys[1], "🚨 reuse ephemeral key ⇒ กุญแจ AES ซ้ำข้ามข้อความ"

    # ทั้งสองอันต้องถอดได้จริง (กัน 'ต่างกันเพราะพัง' ไม่ใช่เพราะสุ่มใหม่)
    for captured in push_server.captured:
        assert json.loads(http_ece.decrypt(
            captured["body"], private_key=browser["priv"],
            auth_secret=browser["raw_auth"], version="aes128gcm",
        )) == _payload()


# ============================================================
# 2) ความล้มเหลวที่ต้องไม่ทำให้คิวพัง
# ============================================================

@pytest.mark.asyncio
async def test_E5_network_failure_returns_none_not_exception(browser):
    """ต่อปลายทางไม่ได้ → คืน **`None`** ไม่ใช่โยน exception

    ⭐ `None` → `_classify()` → `retry` (นโยบาย "push ซ้ำดีกว่า push หาย")
       ถ้าโยน exception ออกมา `process_pending` จะจับได้ก็จริง แต่แถวนั้นจะไม่ได้
       `next_attempt_at` ใหม่ ⇒ **ค้าง retry ทันที**

    ⚠️ หาพอร์ตที่ปิดอยู่จริงด้วยการ bind แล้วปล่อย (ไม่ hardcode 12345 ซึ่งอาจมีคนฟัง)

    mutation ที่ต้องทำให้แตก: ลบ `try/except httpx.HTTPError` → `ConnectError` หลุด
    """
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    dead_port = probe.getsockname()[1]
    probe.close()

    sub = _subscription(f"http://127.0.0.1:{dead_port}/push/x", browser)
    async with httpx.AsyncClient(timeout=2) as client:
        status = await push_service._send_one(client, sub, _payload(), ttl=60)

    assert status is None
    assert push_service._classify(status) == "retry"


@pytest.mark.asyncio
async def test_E6_provider_error_status_is_passed_through(push_server, browser):
    """status ที่ผู้ให้บริการตอบ (เช่น 410 = อุปกรณ์ตาย) ต้องไหลผ่านตรง ๆ

    ⭐ เทสต์นี้ผูก `_send_one` เข้ากับ `_classify`: 410 ต้องกลายเป็น `gone`
       เพื่อให้ `process_pending` ลบ subscription ทิ้ง (เทสต์ T9 ฝั่ง outbox
       พิสูจน์ปลายทางนั้นแล้ว — ที่นี่พิสูจน์ว่าต้นทางส่งค่ามาถูก)
    """
    push_server.status = 410
    sub = _subscription(_endpoint(push_server), browser)

    async with httpx.AsyncClient(timeout=10) as client:
        status = await push_service._send_one(client, sub, _payload(), ttl=60)

    assert status == 410
    assert push_service._classify(status) == "gone"


# ============================================================
# 3) สัญญาของคีย์ (จุดที่ผิดแล้วเงียบที่สุด)
# ============================================================

@pytest.mark.parametrize("size", [16, 32, 48, 65])
@pytest.mark.parametrize("padded", [False, True])
def test_E7_decode_key_accepts_both_spellings(size, padded):
    """`_decode_key` ต้องรับ base64url **ทั้งแบบมีและไม่มี `=`** (ขนาดคือหัวใจของเทสต์นี้)

    ⚠️ **กับดักที่เคยทำให้เทสต์นี้ผ่านทั้งที่ไม่ได้ทดสอบอะไร** — เขียนไว้กันพลาดซ้ำ:
       เดิมใช้ `os.urandom(48)` แล้วต่อท้ายด้วย `"="` คิดว่าเป็น "เคสมี padding"
       แต่ base64 ของ 48 byte = **64 ตัวอักษรพอดี ไม่ต้องมี padding อยู่แล้ว** ⇒
       การต่อ `=` เข้าไปทำให้ได้สตริง *เสีย* ไม่ใช่สตริง *มี padding* และเทสต์ก็ผ่าน
       โดยที่ `_repad()` ถูกถอดออกแล้วก็ยังผ่าน

       ⇒ **ขนาดต้องครอบทั้ง 3 เศษที่เป็นไปได้ของ `len % 3`**:
         `% 3 == 2` → ต้องเติม `=` 1 ตัว (32, 65) · `% 3 == 1` → 2 ตัว (16) · `== 0` → ไม่เติม (48)

    ⭐ ของจริงที่ต้องรอด: `p256dh` = uncompressed point **65 byte** (เติม 1) และ
       `auth` = secret **16 byte** (เติม 2) — สองตัวนี้คือค่าที่เบราว์เซอร์ส่งมาจริง
       และเป็นเหตุที่ `_repad()` มีอยู่ (สเปก Push API ไม่บังคับให้มี padding)

    mutation ที่ต้องทำให้แตก: ตัด `_repad()` ออก → เคส `padded=False` ของ 16/32/65 ล้ม
    """
    raw = os.urandom(size)
    encoded = base64.urlsafe_b64encode(raw).decode()
    # ยืนยันว่าขนาดนี้ "ต้องเติม" จริง — กันกับดักข้างบนกลับมา
    assert (encoded.endswith("=")) != (size % 3 == 0), "ขนาดนี้ไม่ครอบเคส padding ที่ตั้งใจ"

    assert push_service._decode_key(encoded if padded else encoded.rstrip("=")) == raw


@pytest.mark.asyncio
async def test_E8_sign_rejects_non_mailto_subject(push_server, browser, monkeypatch):
    """`sub` ที่ไม่ใช่ mailto:/URL → **py-vapid raise ทันที** (ไม่ใช่ส่งไปเงียบ ๆ)

    ⭐ นี่คือเหตุผลที่ `VAPID_SUBJECT` ใน `core/config.py` มีคอมเมนต์เตือน —
       ถ้าตั้งผิด (เช่นใส่ `admin@example.com` เฉย ๆ ไม่มี `mailto:`) **ทุก push
       จะล้มพร้อมกันทั้งหมด** และผู้ให้บริการไม่ได้บอกอะไร เพราะเราส่งไม่ออกตั้งแต่แรก
       ⇒ `process_pending` จับ exception ต่อแถวไว้ (ดู log "sender โยน exception")
         แล้วแถวนั้นจะ retry จนครบ `PUSH_MAX_ATTEMPTS` แล้วถูกทิ้ง

    ⚠️ เทสต์นี้ **ไม่ยิงเน็ต** — ล้มตั้งแต่ `sign()` ก่อนถึง `client.post()`
    """
    monkeypatch.setattr(settings, "VAPID_SUBJECT", "admin@example.com")
    push_service._reset_vapid_cache()

    sub = _subscription(_endpoint(push_server), browser)
    with pytest.raises(Exception) as err:
        async with httpx.AsyncClient(timeout=5) as client:
            await push_service._send_one(client, sub, _payload(), ttl=60)

    assert "sub" in str(err.value).lower()
    assert push_server.captured == [], "ต้องไม่มีการยิง request ออกไปเลย"


# ============================================================
# 4) `Urgency` — ค่าที่ผิดทำให้ push "ตายทุกอัน" ไม่ใช่แค่ช้า
# ============================================================

@pytest.mark.parametrize("raw", ["high", "HIGH", "  High  ", "NORMAL", "very-low", "low"])
def test_E9_urgency_accepts_valid_values_and_normalizes(raw):
    """ค่าที่ RFC 8030 นิยาม → ผ่าน (ปรับเป็นตัวพิมพ์เล็ก + ตัดช่องว่าง)

    ⭐ `"  High  "` คือเคสที่พังเงียบที่สุดถ้าไม่ `.strip()` — `.env` ที่เขียน
       `PUSH_URGENCY=high ` (เว้นวรรคท้ายบรรทัด) จะกลายเป็นค่าที่ผู้ให้บริการปฏิเสธ
    """
    value = raw.strip().lower()
    with patch.object(settings, "PUSH_URGENCY", raw):
        assert push_service._urgency() == value


@pytest.mark.parametrize("bad", ["", "  ", "urgent", "high ", "critical", "10", "0"])
def test_E10_urgency_rejects_invalid_values_and_falls_back_to_high(bad):
    """ค่าที่ไม่รู้จัก → **ห้ามปล่อยผ่าน** เด็ดขาด

    ⚠️ **ทำไมนี่สำคัญกว่าเรื่องความสวยงาม:** ค่า `Urgency` ที่ผิดจะได้ **400**
       จากผู้ให้บริการ ⇒ `_classify` ตัดสินเป็น `permanent` ⇒ **push ทุกอันตาย**
       โดย in-app ยังทำงานปกติ ⇒ อาการคือ "เปิด push แล้วแต่ไม่มีอะไรเด้งเลย"
       ซึ่งแยกไม่ออกจาก "ผู้ใช้ไม่ได้รับอนุญาต" ด้วยตาเปล่า

    ⇒ เลือก `high` เป็นค่าถอย เพราะอาการของ `normal` คือ "เงียบ" ซึ่งผู้ใช้
      ตีความว่า "พัง" และเราจะไม่รู้ตัวเลย

    mutation ที่ต้องทำให้แตก: `return settings.PUSH_URGENCY` ตรง ๆ → เคส `"urgent"` ล้ม
    """
    with patch.object(settings, "PUSH_URGENCY", bad):
        assert push_service._urgency() == "high"


def test_E11_urgency_constant_matches_rfc8030():
    """ลิสต์ค่าที่อนุญาตต้องตรงกับ RFC 8030 §5.3 เป๊ะ — เพิ่ม/ลดไม่ได้

    ⚠️ `"normal"` **ต้องอยู่ในลิสต์** — เป็นค่า default ของสเปก ถ้าถอดออก
       จะทำให้ทุกคนที่ตั้ง `normal` โดยเจตนาโดนปรับเป็น `high` เงียบ ๆ (กินแบตขึ้น)
    """
    assert push_service._URGENCIES == {"very-low", "low", "normal", "high"}
