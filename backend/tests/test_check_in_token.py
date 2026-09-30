"""
🎟️ D2 — โทเคนบัตรเช็คอิน (`core/check_in_token.py`) — **เทสต์บริสุทธิ์ ไม่แตะ DB**

แยกออกจาก `test_events.py` โดยเจตนา: ไฟล์นั้นเป็น integration ทั้งไฟล์ (ต้องมี Postgres)
แต่ตรรกะของโทเคนเป็นคณิตศาสตร์ล้วน ๆ ⇒ ทดสอบได้ในมิลลิวินาที และ **ทดสอบได้ครบทุกเส้น**
(โดยเฉพาะเส้นที่ยิงผ่าน HTTP ยาก: ไบต์ที่ถูกแก้ · ลายเซ็นผิดยาว · ตัวเลข overflow)

⭐ **สิ่งที่เทสต์ชุดนี้ปกป้อง** — ถ้ามีคน "ทำความสะอาด" แล้วเปลี่ยน `compare_digest` เป็น `==`
   หรือถอด `event_id` ออกจากข้อความที่ลงนาม เทสต์จะแดงทันที · ทั้งสองอย่างเป็นข้อผิดพลาด
   ที่ **โค้ดยังทำงานถูกในเครื่องทดสอบทุกกรณี** และไปพังเฉพาะกับคนที่ตั้งใจโจมตี
"""
import base64
import hashlib
import hmac

import pytest

from core.check_in_token import PREFIX, _SIGNING_CONTEXT, make, parse
from core.config import settings


def _sig_of(event_id: int, registration_id: int) -> str:
    """ลายเซ็นที่ถูกต้อง — คำนวณซ้ำจากนิยามในเอกสาร ไม่ได้เรียกใช้ฟังก์ชันที่กำลังทดสอบ"""
    message = f"{_SIGNING_CONTEXT}:{event_id}:{registration_id}".encode()
    digest = hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest[:16]).decode().rstrip("=")


# ============================================================
# 1) วงกลมปกติ
# ============================================================

def test_round_trip():
    token = make(12, 345)
    assert parse(token) == (12, 345)


def test_prefix_and_shape():
    """รูปแบบต้องเป็น `PIRI-EVT1:<event>:<reg>:<sig>` — 4 ชิ้น คั่นด้วย `:`"""
    parts = make(7, 9).split(":")
    assert parts[0] == PREFIX
    assert parts[1] == "7"
    assert parts[2] == "9"
    assert parts[3] == _sig_of(7, 9)


@pytest.mark.parametrize("event_id,reg_id", [(1, 1), (1, 999999), (999999, 1), (12345, 67890)])
def test_round_trip_many(event_id, reg_id):
    assert parse(make(event_id, reg_id)) == (event_id, reg_id)


def test_token_is_deterministic():
    """บัตรใบเดิมต้องได้รหัสเดิม **ทุกครั้ง** — ไม่งั้น QR ที่แสดงค้างไว้จะเปลี่ยนเอง
    แล้วนักเรียนที่แคปจอไว้จะถือบัตรคนละใบกับที่หน้าเว็บโชว์"""
    assert make(3, 4) == make(3, 4)


def test_does_not_leak_other_pairs():
    """ค่า (7, 9) ต้องไม่ให้โทเคนเดียวกับ (9, 7) — ลำดับมีความหมาย"""
    assert make(7, 9) != make(9, 7)


# ============================================================
# 2) ★ การปลอม — หัวใจของไฟล์นี้
# ============================================================

def test_signature_is_not_a_plain_hash():
    """ลายเซ็นต้องผูกกับ `SECRET_KEY` — ไม่ใช่ hash ของ payload เฉย ๆ

    ⚠️ ถ้าเขียนเป็น `sha256(payload)` ใครก็คำนวณได้ ⇒ บัตรปลอมทำได้ด้วยเครื่องคิดเลข
       ในเบราว์เซอร์ (มีเว็บทำ QR ให้ฟรี) ⇒ เทสต์นี้คือด่านเดียวที่จับได้
    """
    assert _sig_of(5, 6) != hashlib.sha256(f"{PREFIX}:5:6".encode()).hexdigest()[:22]


def test_tampered_signature_is_rejected():
    token = make(5, 6)
    head, sig = token.rsplit(":", 1)
    # พลิกตัวอักษรสุดท้ายเป็นตัวอื่น (ไม่ใช่ตัวเดิม)
    flipped = "A" if sig[-1] != "A" else "B"
    assert parse(f"{head}:{sig[:-1]}{flipped}") is None


def test_tampered_registration_id_is_rejected():
    """⭐ เคสโจมตีจริง: แก้เลขใบสมัครเป็นของเพื่อน แล้วใช้ลายเซ็นเดิม

    ถ้าลายเซ็นไม่ครอบ `registration_id` (เช่นลงนามแค่ event_id) เทสต์นี้จะ **ผ่าน**
    ทั้งที่ระบบเปิดช่องให้เช็คอินแทนกันได้ด้วยการแก้เลขใน QR
    """
    token = make(5, 6)
    parts = token.split(":")
    assert parse(":".join([parts[0], parts[1], "7", parts[3]])) is None


def test_tampered_event_id_is_rejected():
    token = make(5, 6)
    parts = token.split(":")
    assert parse(":".join([parts[0], "6", parts[2], parts[3]])) is None


def test_signature_of_other_context_is_rejected():
    """โดเมนต้องแยกจากข้อความอื่นที่ลงนามด้วย `SECRET_KEY` เดียวกัน

    ⇒ ลายเซ็นที่คำนวณจากข้อความดิบ (ไม่มี `_SIGNING_CONTEXT`) ต้องไม่ผ่าน
    """
    message = f"5:6".encode()
    digest = hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).digest()
    wrong = base64.urlsafe_b64encode(digest[:16]).decode().rstrip("=")
    assert parse(f"{PREFIX}:5:6:{wrong}") is None


def test_wrong_prefix_is_rejected():
    token = make(5, 6)
    assert parse(token.replace(PREFIX, "PIRI-EVT2")) is None
    assert parse("PIRI:5:6:" + _sig_of(5, 6)) is None


# ============================================================
# 3) รูปแบบเพี้ยน — ต้องคืน None ไม่ใช่ระเบิด
# ============================================================

@pytest.mark.parametrize("bad", [
    "",                      # ว่าง
    "   ",                   # ช่องว่างล้วน
    "PIRI-EVT1",             # ไม่มีอะไรเลย
    "PIRI-EVT1:5:6",         # ขาดลายเซ็น
    "PIRI-EVT1:5:6:aa:bb",   # ชิ้นเกิน
    "PIRI-EVT1:5:6:",        # ลายเซ็นว่าง (ต้องไม่ผ่านทั้งที่ `_sig_of` ไม่มีทางว่าง)
    "PIRI-EVT1::6:xx",       # event_id ว่าง
    "PIRI-EVT1:5::xx",       # registration_id ว่าง
    "PIRI-EVT1:5x:6:" + _sig_of(5, 6),   # ตัวอักษรปนในตัวเลข
    "PIRI-EVT1:5.0:6:" + _sig_of(5, 6),  # ทศนิยม
    "PIRI-EVT1:-5:6:" + _sig_of(5, 6),   # ติดลบ
    "PIRI-EVT1:0:6:" + _sig_of(5, 6),    # 0 ไม่ใช่ id ของ SERIAL
    "PIRI-EVT1:5:0:" + _sig_of(5, 0),
    None,                    # ไม่ใช่สตริงเลย (ผู้เรียกพลาดส่ง)
    12345,                   # ตัวเลข
])
def test_malformed_returns_none(bad):
    assert parse(bad) is None


def test_surrounding_whitespace_is_tolerated():
    """ผู้ใช้อาจคัดลอกรหัสที่มีช่องว่างติดมา (คัดลอกจากหน้าจอ/แชท) — ไม่ควรพังเพราะเรื่องนั้น"""
    assert parse(f"  {make(5, 6)}  ") == (5, 6)


def test_extra_colon_inside_token_does_not_confuse():
    """ลายเซ็นเป็น base64url ⇒ **ไม่มี `:`** · ถ้าวันหน้าเปลี่ยนไปใช้อักขระที่มี `:`
    การ split จะพังทันที — เทสต์นี้ตรึงข้อสมมติไว้"""
    assert ":" not in make(1, 2).rsplit(":", 1)[1]
