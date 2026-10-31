"""Schema ของ `/api/version` — บอกว่า backend ที่กำลังรันเป็น build ไหน"""

from pydantic import BaseModel


class VersionOut(BaseModel):
    version: str
    commit: str
