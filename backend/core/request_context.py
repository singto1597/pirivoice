"""
📡 Request Context — เก็บข้อมูลของ request/งานปัจจุบัน (contextvar)

ใช้ให้ AuditLogger เก็บ ip_address / user_agent / endpoint_or_command / trace_id /
execution_time_ms อัตโนมัติโดยไม่ต้องแก้ signature ของ service ทุกตัว:
- HTTP: middleware ใน main.py ตั้ง context ตอนรับ request → services/logger อ่านได้
- งานที่ไม่ผ่าน HTTP (ARQ worker / script): ครอบด้วย `audit_scope()` เพื่อให้ได้ context ชุดเดียวกัน
- จบงาน → clear (กัน leak ข้าม request)

⚠️ ทุกคอลัมน์ของ audit_logs ต้องไม่เว้นว่าง — context ที่ว่างคือต้นเหตุที่ค่าเป็น NULL
   งานที่ไม่ได้ผ่าน HTTP จึงต้องเรียก `audit_scope()` เสมอ (ดู core/logger.py)
"""
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Dict, Iterator, Optional

_AUDIT_CTX: ContextVar[Dict] = ContextVar("audit_ctx", default={})


def set_audit_context(
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    trace_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    started_at: Optional[float] = None,
) -> None:
    """ตั้ง context ของงานปัจจุบัน (เรียกจาก middleware หรือ audit_scope)

    started_at = เวลาเริ่มงานจาก time.monotonic() ใช้คำนวณ execution_time_ms
    (ถ้าไม่ส่งมา จะเริ่มนับจากตอนนี้เลย)
    """
    _AUDIT_CTX.set({
        "ip_address": ip_address,
        "user_agent": user_agent,
        "trace_id": trace_id,
        "endpoint": endpoint,
        "started_at": time.monotonic() if started_at is None else started_at,
    })


def get_audit_context() -> Dict:
    """อ่าน context ปัจจุบัน (ค่า default = {} ถ้ายังไม่ตั้ง)"""
    return _AUDIT_CTX.get()


def clear_audit_context() -> None:
    """ล้าง context (เรียกหลังงานจบ — กัน leak ข้าม request)"""
    _AUDIT_CTX.set({})


@contextmanager
def audit_scope(
    endpoint: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Iterator[Dict]:
    """ครอบงานที่ไม่ได้ผ่าน HTTP (ARQ worker / script) ให้มี audit context เหมือน request

    ใช้แบบนี้:
        with audit_scope(endpoint=f"arq:process_student_import job_id={job_id}"):
            await import_service.process_import_job(pool, job_id)

    - ตั้ง trace_id ให้เองถ้าไม่ส่งมา (ทุก log ในงานเดียวจะได้ trace_id เดียวกัน — ตามรอยได้)
    - started_at = ตอนเข้า scope → execution_time_ms ของทุก log ในงานนี้วัดจากจุดเดียวกัน
    - คืน context เดิมกลับเมื่อออกจาก scope (ซ้อนกันได้)
    """
    previous = _AUDIT_CTX.get()
    set_audit_context(
        ip_address=ip_address,
        user_agent=user_agent,
        trace_id=trace_id or str(uuid.uuid4()),
        endpoint=endpoint,
    )
    try:
        yield _AUDIT_CTX.get()
    finally:
        _AUDIT_CTX.set(previous)
