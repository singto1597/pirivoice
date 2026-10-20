"""
Pydantic Schemas สำหรับระบบ Import นักเรียนจาก Excel แบบ Queue
===============================================================
Endpoints:
- POST /api/upload-student-excel      → ImportJobOut (status=PENDING)
- POST /api/start-import-job/{id}     → ImportJobOut (status=QUEUED)
- GET  /api/import-jobs               → list[ImportJobOut]
"""
import json
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

# สถานะของงาน (ตรงกับตาราง student_import_jobs)
IMPORT_STATUS_PENDING = "PENDING"
IMPORT_STATUS_QUEUED = "QUEUED"
IMPORT_STATUS_PROCESSING = "PROCESSING"
IMPORT_STATUS_COMPLETED = "COMPLETED"
IMPORT_STATUS_FAILED = "FAILED"

# สถานะที่ start ได้ (รอเริ่ม / ล้มเหลวแล้วลองใหม่) — QUEUED ห้ามกดซ้ำ (กันยิงคิวซ้ำ)
RESTARTABLE_STATUS = {IMPORT_STATUS_PENDING, IMPORT_STATUS_FAILED}

# สถานะที่ worker ดำเนินการต่อได้ตอน "claim" งาน
CLAIMABLE_STATUS = {IMPORT_STATUS_PENDING, IMPORT_STATUS_QUEUED}


def compute_progress_percent(total_rows: int, processed_rows: int) -> int:
    """คำนวณ % ความคืบหน้า (0-100) สำหรับ progress bar"""
    if not total_rows:
        return 100 if processed_rows else 0
    pct = round(processed_rows / total_rows * 100)
    return max(0, min(100, pct))


class ImportJobOut(BaseModel):
    """ข้อมูลงาน import ที่ส่งกลับให้ Frontend (ตัด file_path ออก — internal)"""
    id: int
    file_name: str
    status: str = Field(description="PENDING / QUEUED / PROCESSING / COMPLETED / FAILED")
    total_rows: int = 0
    processed_rows: int = 0
    imported_count: int = 0
    skipped_count: int = 0
    error_logs: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    progress_percent: int = 0
    created_by: Optional[int] = None
    # 🌟 P6 — ปีที่ job นี้ import เข้า (NULL = ใช้ปีปัจจุบันของโรงเรียน ณ ตอนประมวลผล)
    academic_year_id: Optional[int] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @classmethod
    def from_db_row(cls, row) -> "ImportJobOut":
        """แปลง asyncpg record / dict → schema (รวมคำนวณ progress_percent)"""
        data = dict(row) if not isinstance(row, dict) else row
        # error_logs เป็น JSONB — asyncpg คืนเป็น string (เช่น '[]') → ต้อง parse ให้เป็น list
        raw_logs = data.get("error_logs")
        if isinstance(raw_logs, str):
            try:
                raw_logs = json.loads(raw_logs)
            except (ValueError, TypeError):
                raw_logs = []
        return cls(
            id=data["id"],
            file_name=data["file_name"],
            status=data["status"],
            total_rows=data["total_rows"],
            processed_rows=data["processed_rows"],
            imported_count=data["imported_count"],
            skipped_count=data["skipped_count"],
            error_logs=list(raw_logs or []),
            error_message=data.get("error_message"),
            progress_percent=compute_progress_percent(data["total_rows"], data["processed_rows"]),
            created_by=data.get("created_by"),
            academic_year_id=data.get("academic_year_id"),
            created_at=data["created_at"],
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
        )
