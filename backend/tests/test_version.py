# === Version API Tests: /api/version ===
# endpoint นี้ไม่ต้องล็อกอิน และไม่แตะฐานข้อมูล — ใช้บอกว่า build ที่รันอยู่คืออะไร
from core.config import settings


def test_version_reports_project_version(client):
    res = client.get("/api/version")
    assert res.status_code == 200
    body = res.json()
    assert body["version"] == settings.PROJECT_VERSION
    assert body["commit"] == settings.GIT_SHA


def test_version_is_not_cached(client):
    """ถ้าแคชไว้ ผู้ใช้จะเห็นเวอร์ชันเก่าหลัง deploy"""
    res = client.get("/api/version")
    assert res.headers["cache-control"] == "no-store"


def test_openapi_version_matches_project_version(client):
    """หน้า /openapi.json ต้องรายงานเลขเดียวกับ PROJECT_VERSION ไม่ใช่ค่าตกค้าง"""
    res = client.get("/openapi.json")
    assert res.status_code == 200
    assert res.json()["info"]["version"] == settings.PROJECT_VERSION
