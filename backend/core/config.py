import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "PIRIvoice API (ระบบรับฟังความคิดเห็นและปัญหาสภานักเรียน)"
    PROJECT_VERSION: str = "1.0.0"

    DATABASE_URL: str
    API_KEY: str
    SECRET_KEY: str
    SUPER_ADMIN_ID: int = 0

    # JWT Settings
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200  # 30 days

    # Redis (สำหรับ event/notification — อาจยังไม่ใช้ใน v1 แต่ config ให้พร้อม)
    REDIS_URL: str = ""

    # Queue Import นักเรียนจาก Excel (ARQ Worker)
    # - IMPORT_STORAGE_DIR: โฟลเดอร์เก็บไฟล์ .xlsx ที่อัปโหลด (shared volume ระหว่าง backend + worker)
    #   ใน Docker = /data/imports (mount จาก docker-compose.app.yml) ; dev ในเครื่อง = ตั้งเองใน .env
    IMPORT_STORAGE_DIR: str = "/data/imports"
    # จำกัดขนาดไฟล์ Excel ที่รับอัปโหลด (MB) — ป้องกันไฟล์ยักษ์ลาก worker
    IMPORT_FILE_SIZE_LIMIT_MB: int = 10
    # จำนวนแถวต่อ 1 batch เมื่อ worker ทยอย insert (คุมหน่วยความจำ + ความถี่ของการ update progress)
    IMPORT_BATCH_SIZE: int = 50
    # จำนวนแถวสูงสุดต่อไฟล์ (กันไฟล์ยักษ์ลาก worker นานเป็นชั่วโมง — DoS)
    IMPORT_MAX_ROWS: int = 5000
    # อายุงานค้าง (นาที) ที่ worker กู้คืนตอนเริ่มต้น — PROCESSING/QUEUED ค้างเกินนี้ → reset กลับ QUEUED
    IMPORT_RECOVERY_STALE_MINUTES: int = 35

    # Seed users (admin/ครูสภา/ประธานสภา) ตอนเปิดระบบครั้งแรก — ไฟล์เก็บ username+รหัสชั่วคราว
    SEED_CREDENTIALS_FILE: str = "default_admin_credentials.txt"

    # ============================================================
    # 🔔 Web Push (A3)
    # ============================================================
    # ⭐ **ทุกตัวมี default — dev/test รันได้โดยไม่ต้องมีคีย์** และ `.env` ที่ยังไม่ตั้ง
    #    จะไม่ทำให้ระบบล่ม (pydantic-settings จะ raise ถ้าไม่มี default)
    #
    # ⚠️ **`VAPID_PUBLIC_KEY` ว่าง = ปิด push ทั้งระบบ** (in-app ยังทำงานปกติ)
    #    นี่คือ **สวิตช์ปิดฉุกเฉินที่ไม่ต้อง deploy** — ถ้า push เริ่มสร้างปัญหา
    #    (สแปมนักเรียน / ปลายทางล่ม / ค่าใช้จ่าย) ให้ลบค่าสองตัวนี้ออกจาก `.env`
    #    แล้ว `docker service update --force` ⇒ worker จะ mark outbox เป็น
    #    `vapid-not-configured` แล้วหยุดยิง (ไม่ใช่ปล่อยให้คิวโตไม่หยุด)
    VAPID_PUBLIC_KEY: str = ""
    # ⚠️ **rotate private key = subscription เดิมทั้งหมดใช้ไม่ได้ทันที** (เบราว์เซอร์ผูก
    #    subscription กับ public key ตอน subscribe) ⇒ ต้อง
    #    `DELETE FROM push_subscriptions;` แล้วให้นักเรียนกดเปิด push ใหม่ทุกคน
    VAPID_PRIVATE_KEY: str = ""
    # `sub` claim ของ VAPID JWT — RFC 8292 บังคับให้เป็น `mailto:` หรือ URL
    # ⚠️ `py_vapid` **validate รูปแบบนี้** และจะ raise ถ้าไม่ใช่ (ไม่ใช่แค่เตือน)
    VAPID_SUBJECT: str = "mailto:admin@example.com"
    # จำนวน outbox แถวที่ claim ต่อรอบ (20 วิ) — คุมหน่วยความจำและขนาด batch
    PUSH_BATCH_SIZE: int = 100
    # เพดานการลองใหม่ก่อนทิ้ง — 5 ครั้งด้วย exponential backoff (30, 60, 120, 240, 480 วิ)
    PUSH_MAX_ATTEMPTS: int = 5
    # ⏰ **ด่านกัน push storm**: ถ้า worker ล่มไป 3 ชม. แล้วกลับมา คิวจะสะสมแจ้งเตือน
    #    เก่าหลายพันรายการพร้อมกัน ⇒ ผู้ใช้ได้ push พรวดเดียวทั้งหน้าจอ
    #    เกินอายุนี้ = mark processed ทันทีโดยไม่ส่ง (`last_error = 'stale'`)
    PUSH_MAX_AGE_MINUTES: int = 15
    # ⏱️ **ด่านกู้แถวที่ worker ตายกลางคัน** — แถวที่ถูก claim แล้วค้าง (`processing_at`
    #    ไม่เป็น NULL) จะไม่มีวันถูกหยิบอีก ถ้าไม่มีตัวนี้มากู้
    #    🚨 **ต้องน้อยกว่า `PUSH_MAX_AGE_MINUTES` เสมอ** ไม่งั้นแถวที่กู้คืนมาจะถูก
    #       mark stale ทันทีในรอบเดียวกัน ⇒ ด่านนี้ไม่ได้ช่วยให้ push ถึงมือใครเลย
    #    ที่มา: worker `job_timeout = 120` วินาที ⇒ ค้างเกิน 5 นาที = ตายแน่นอน
    PUSH_RECOVER_MINUTES: int = 5
    # เก็บแถว outbox ที่ processed แล้วกี่วัน (คิวที่ยังไม่ processed **ไม่ถูกลบ**)
    PUSH_RETENTION_DAYS: int = 7
    # จำนวน HTTP request ที่ยิงพร้อมกัน — fanout 1,000 คนต้องมีเพดาน ไม่งั้นเปิด
    # connection ออกไป 1,000 เส้นพร้อมกัน (และ FCM จะตอบ 429 กลับมา)
    PUSH_SEND_CONCURRENCY: int = 20
    # TTL ของ push message (วินาที) — บอกปลายทางว่า "ถ้าไม่ออนไลน์ เก็บไว้กี่วิ"
    # 3600 = 1 ชม. ตรงกับ `PUSH_MAX_AGE_MINUTES` เชิงแนวคิด (ไม่ส่งของเก่าเกิน 1 ชม.)
    PUSH_TTL_SECONDS: int = 3600

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
