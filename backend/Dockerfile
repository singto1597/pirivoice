# ใช้ Base Image ตามที่ระบุ
FROM python:3.12-slim

# ตั้งค่า Environment Variables เพื่อปรับแต่งการทำงานของ Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# กำหนด Working Directory ภายใน Container
WORKDIR /app

# ติดตั้ง System Dependencies ที่จำเป็น (เช่น สำหรับคอมไพล์แพ็กเกจบางตัว) 
# และลบ Cache ทิ้งทันทีเพื่อประหยัดพื้นที่
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# คัดลอกไฟล์ requirements.txt และติดตั้ง Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# สร้าง User แบบ Non-root เพื่อความปลอดภัยในระดับ Production
# /data/imports = โฟลเดอร์เก็บไฟล์ Excel ที่อัปโหลด (mount เป็น named volume ใน compose)
#   → ต้องเป็นเจ้าของโดย appuser ตั้งแต่แรก เพื่อให้ volume ใหม่ที่สร้าง inherits ownership ถูกต้อง
RUN adduser --disabled-password --gecos "" appuser && \
    chown -R appuser /app && \
    mkdir -p /data/imports && chown -R appuser:appuser /data
USER appuser

# คัดลอก Source Code ทั้งหมดเข้าสู่ Container
COPY --chown=appuser:appuser . .

# commit ที่ build image นี้ — pull_all.sh / setup.sh ส่ง IMAGE_TAG เข้ามา
# วางหลัง COPY เพื่อไม่ให้ทุก commit ทำให้ชั้น apt/pip ข้างบน cache แตก
# worker / push_worker ใช้ image เดียวกันจึงได้ค่านี้ไปด้วยโดยไม่ต้องแก้ compose
ARG GIT_SHA=unknown
ENV GIT_SHA=${GIT_SHA}

# กำหนด Port ที่ Container จะเปิดรับการเชื่อมต่อ
EXPOSE 8000

# คำสั่งรัน Uvicorn สำหรับ Production
# มีการใช้ --proxy-headers และ --forwarded-allow-ips เพื่อให้ระบบอ่านค่า IP และ HTTPS Schema ได้ถูกต้อง 
# ซึ่งจำเป็นมากสำหรับการทำ Discord OAuth2 Redirect
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]