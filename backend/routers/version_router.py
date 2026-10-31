"""Version Router — `/api/version`

ใช้ตอบว่า backend ที่กำลังรันอยู่นั้นเป็นเวอร์ชันอะไรและ build จาก commit ไหน
- `version` มาจาก `PROJECT_VERSION` ใน `core/config.py` (release.sh sync ให้ตรงกับ tag)
- `commit` มาจาก build arg `GIT_SHA` ที่ `pull_all.sh`/`setup.sh` ส่งเข้า image
  ⚠️ ไม่ได้อ่านจาก `.git` เพราะ image ไม่มี `.git` อยู่ในนั้น

ตั้ง `Cache-Control: no-store` เพราะค่านี้ต้องตรงกับ build ที่รันอยู่จริง
ถ้า Cloudflare หรือเบราว์เซอร์แคชไว้ จะเหมือน deploy ไม่ขึ้น
"""
from fastapi import APIRouter, Response

from core.config import settings
from models.version_schemas import VersionOut

router = APIRouter(tags=["Version"])


@router.get("/version", response_model=VersionOut)
async def get_version(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return VersionOut(version=settings.PROJECT_VERSION, commit=settings.GIT_SHA)
