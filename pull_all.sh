#!/bin/bash

# 1. โหลดตัวแปรจากไฟล์ .env นอกสุด
if [ -f .env ]; then
    set -a
    . ./.env
    set +a
    echo "⚙️ โหลด Environment: $ENV_NAME"
else
    echo "❌ ไม่พบไฟล์ .env"
    exit 1
fi

CURRENT_BRANCH=$(git branch --show-current)
if [ -z "$CURRENT_BRANCH" ]; then
    echo "❌ ไม่สามารถหาชื่อ Branch ได้"
    exit 1
fi

# 2. ดึงโค้ดล่าสุดจาก Monorepo
echo "⬇️ กำลังดึงโค้ดล่าสุดจาก Monorepo..."
git fetch origin
git reset --hard origin/$CURRENT_BRANCH

# --- 📦 [NEW] ดึงไฟล์จริงจาก Git LFS (webp/pdf ของ P.R. Playbooks) ---
# git reset --hard จะได้ไฟล์เป็น LFS pointer (ไฟล์เล็กๆ) ไม่ใช่ไฟล์จริง
# ต้อง git lfs pull ก่อน build ไม่งั้น Docker COPY เอาตัวชี้ไปลง image → รูปไม่แสดง
#
# ⚠️ ใช้ absolute path ของ git-lfs (ไม่ใช่ command -v git-lfs) เพราะ script นี้
#    มักถูกรันแบบ non-interactive ซึ่ง ~/.local/bin ไม่อยู่ใน PATH → command -v หาไม่เจอ
#    และหลัง pull ต้องตรวจว่าไฟล์เป็นไฟล์จริง (ใหญ่พอ) ไม่ใช่ pointer 131 bytes
#    ⚠️ ตรวจทุกไฟล์ ไม่ใช่แค่ไฟล์เดียว — ถ้า pull ถูกตัดกลางคัน (เน็ต/DNS เดี้ยง)
#       จะได้ไฟล์จริงแค่บางส่วน → ต้องลอง pull ซ้ำจนครบทุก vol
echo "📦 กำลังดึงไฟล์จริงจาก Git LFS..."
LFS_BIN=""
if command -v git-lfs >/dev/null 2>&1; then
    LFS_BIN="git-lfs"
elif [ -x "$HOME/.local/bin/git-lfs" ]; then
    LFS_BIN="$HOME/.local/bin/git-lfs"
fi

if [ -z "$LFS_BIN" ]; then
    echo "❌ ไม่พบ git-lfs — ไฟล์ webp/pdf จะเป็น pointer (รูปไม่แสดง) หยุด deploy"
    exit 1
fi

# ลอง pull สูงสุด 3 รอบ (กันเน็ต/DNS ขัดข้องชั่วคราว) แล้วตรวจว่าครบทุกไฟล์จริง
PLAYBOOK_DIR="frontend/public/playbooks"
LFS_OK=0
for attempt in 1 2 3; do
    echo "  (รอบ $attempt) git lfs pull..."
    if "$LFS_BIN" pull; then
        # 🧪 ตรวจว่าไม่มีไฟล์ใดเหลือเป็น pointer (ขนาด < 1000 bytes = pointer 131 bytes)
        TOTAL=$(find "$PLAYBOOK_DIR" -type f \( -name "*.webp" -o -name "*.pdf" \) 2>/dev/null | wc -l)
        POINTERS=$(find "$PLAYBOOK_DIR" -type f \( -name "*.webp" -o -name "*.pdf" \) -size -1000c 2>/dev/null | wc -l)
        if [ "$POINTERS" -eq 0 ] && [ "$TOTAL" -gt 0 ]; then
            echo "✅ ไฟล์ LFS ทั้งหมด $TOTAL ไฟล์เป็นไฟล์จริงแล้ว (ไม่มี pointer เหลือ)"
            LFS_OK=1
            break
        fi
        echo "  ⚠️ ยังมีไฟล์เป็น pointer เหลือ $POINTERS/$TOTAL ไฟล์ — ลองรอบถัดไป..."
    else
        echo "  ⚠️ git lfs pull รอบที่ $attempt ล้มเหลว — ลองรอบถัดไป..."
    fi
done

if [ "$LFS_OK" -ne 1 ]; then
    echo "❌ ดึงไฟล์ LFS ไม่ครบ (ยังมี pointer เหลือ) — ตรวจสอบเน็ต/DNS ของเครื่อง แล้วรัน pull_all.sh ใหม่"
    find "$PLAYBOOK_DIR" -type f \( -name "*.webp" -o -name "*.pdf" \) -size -1000c 2>/dev/null | head -10
    exit 1
fi

# --- 🚀 [NEW] ดึงเลข Commit 7 หลักล่าสุดมาใช้เป็นชื่อ Image ---
export IMAGE_TAG=$(git rev-parse --short HEAD)
echo "🏷️ ตรวจพบ Commit ล่าสุด: ${IMAGE_TAG}"

# 3. เตรียมไฟล์ .env ให้ Frontend (Vite) ก่อน Build
# echo "📝 คัดลอก .env โยนให้ Frontend..."
# cp .env frontend/.env

# 4. Build Image (ใช้เลข Commit เป็น Tag แทน latest)
echo "🔨 กำลังสร้าง Docker Image เวอร์ชัน: ${IMAGE_TAG}..."
docker build \
  --build-arg GIT_SHA=${IMAGE_TAG} \
  -t pirivoice-${ENV_NAME}-backend:${IMAGE_TAG} ./backend
docker build --no-cache \
  --build-arg VITE_API_BASE_URL=${VITE_API_BASE_URL} \
  -t pirivoice-${ENV_NAME}-frontend:${IMAGE_TAG} ./frontend

# 5. Deploy อัปเดตระบบแบบ Zero Downtime
echo "🚀 กำลังสลับสวิตช์ระบบ $ENV_NAME แบบ Zero Downtime (เวอร์ชัน ${IMAGE_TAG})..."
docker stack deploy -c docker-compose.app.yml ${ENV_NAME}_app

echo "✅ อัปเดตเสร็จสมบูรณ์ ระบบทำงานต่อเนื่องไม่มีสะดุด!"
