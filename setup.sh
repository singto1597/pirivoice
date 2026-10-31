#!/bin/bash
# =====================================================================
# 🚀 setup.sh — เริ่มต้นระบบ PIRIvoice แบบปุ่มเดียวจบ (One-Shot Boot)
#
# รัน 1 ครั้งจบทุกอย่าง:
#   1) เปิด Docker Swarm (ถ้ายังไม่เคยเปิด)
#   2) สร้าง Docker Networks ทั้งหมดจากชื่อใน .env (รวม traefik-public)
#   3) ตรวจ Traefik Proxy — ถ้ายังไม่มี แนะนำติดตั้งครั้งเดียว (./setup_traefik.sh)
#   4) รัน Infrastructure (PostgreSQL + Redis)
#   5) Build Docker Image + Deploy แอป (backend ×3 / frontend ×3 / worker ×1)
#
# 🎯 Traefik เป็นตัวกลาง 1 เครื่อง 1 อัน (ติดตั้งครั้งเดียวด้วย ./setup_traefik.sh)
#    ทุกระบบ / หลาย environment แชร์ตัวเดียวกันผ่าน network "traefik-public"
#    สคริปต์นี้ไม่ deploy Traefik — แค่ตรวจว่ามีอยู่ไหม
#    ทุกชื่อ (network / stack / volume / image) อ้างอิงจาก ENV_NAME ใน .env
#    อยากได้ environment ใหม่ (เช่น staging → production) แค่แก้ ENV_NAME
#    ใน .env แล้วรัน ./setup.sh ใหม่ — ระบบสร้างชุดใหม่ให้ทันที (ข้อมูลเก่าคงอยู่)
#
# ตัวเลือก:
#   ./setup.sh              # ทำทุกอย่าง (ใช้ครั้งแรก / ตั้ง environment ใหม่)
#   ./setup.sh --no-build   # ข้าม build ใช้ image ที่มีอยู่ (เร่งเวลา rerun)
#   ./setup.sh --help       # ดูวิธีใช้
# =====================================================================
set -euo pipefail

cd "$(dirname "$0")"

# ---------- helper ----------
red()    { printf "\033[1;31m%s\033[0m\n" "$*"; }
green()  { printf "\033[1;32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[1;33m%s\033[0m\n" "$*"; }
cyan()   { printf "\033[1;36m%s\033[0m\n" "$*"; }
step()   { echo; cyan "▶ $*"; }

usage() {
    awk 'NR>=3 && /^# ===/ { exit } NR>=3 && /^#/ { gsub(/^# ?/, ""); print }' "$0"
    exit 0
}

# ---------- อ่าน flags ----------
NO_BUILD=0
for arg in "$@"; do
    case "$arg" in
        --no-build) NO_BUILD=1 ;;
        -h|--help)  usage ;;
        *)          yellow "⚠️  ไม่รู้จักตัวเลือก: $arg (ดู ./setup.sh --help)" ;;
    esac
done

# =====================================================================
# 1) โหลด .env
# =====================================================================
step "โหลดไฟล์ .env"
if [ ! -f .env ]; then
    red "❌ ไม่พบไฟล์ .env"
    echo "   คัดลอกก่อน:  cp .env.example .env"
    echo "   แล้วแก้ค่าให้ครบ: อย่างน้อย ENV_NAME, API_DOMAIN, WEB_DOMAIN, POSTGRES_USER/PASSWORD/DB, VITE_API_BASE_URL"
    exit 1
fi

# source ทุกตัวแปร (export) — docker stack deploy อ่านจาก environment ตรงนี้ได้เลย
set -a
. ./.env
set +a

if [ -z "${ENV_NAME:-}" ]; then
    red "❌ ไม่พบ ENV_NAME ใน .env"
    exit 1
fi
green "   ✔ โหลด .env แล้ว (ENV_NAME=$ENV_NAME)"

# ---------- ตรวจ Docker ----------
if ! command -v docker >/dev/null 2>&1; then
    red "❌ ไม่พบคำสั่ง docker ในเครื่อง"
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    red "❌ Docker daemon ไม่ทำงาน — เปิด Docker ก่อน (เช่น systemctl start docker หรือเปิด Docker Desktop)"
    exit 1
fi

# ---------- ตรวจค่าจำเป็น ----------
# ENV_NAME ใช้เป็นชื่อ network/stack/volume/image ต้องเป็นชื่อที่ docker รับได้
if ! [[ "$ENV_NAME" =~ ^[a-z0-9][a-z0-9_.-]*$ ]]; then
    red "❌ ENV_NAME=\"$ENV_NAME\" ใช้ไม่ได้ — ใช้ตัวอักษรพิมพ์เล็ก/ตัวเลข/_/- เท่านั้น เช่น staging, production"
    exit 1
fi
if [ "$ENV_NAME" = "staging_or_production" ]; then
    yellow "⚠️  ENV_NAME ยังเป็นค่า placeholder (staging_or_production)"
    yellow "    ยังรันได้แต่ชื่อจะดูแปลก — แนะนำแก้ .env ตั้งเป็น staging หรือ production"
fi

for v in API_DOMAIN WEB_DOMAIN POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB VITE_API_BASE_URL; do
    if [ -z "${!v:-}" ]; then
        red "❌ ยังไม่ได้ตั้ง $v ใน .env"
        exit 1
    fi
done

# =====================================================================
# 2) เปิด Docker Swarm (ถ้ายังไม่เคยเปิด)
# =====================================================================
step "1/5 ตรวจสอบ Docker Swarm"
if docker node ls >/dev/null 2>&1; then
    green "   ✔ Swarm เปิดอยู่แล้ว"
else
    echo "   ⏳ กำลังเปิดโหมด Swarm (docker swarm init)..."
    docker swarm init
    green "   ✔ Swarm พร้อมใช้แล้ว"
fi

# =====================================================================
# 3) สร้าง Networks (ทุกชื่อสร้างจาก ENV_NAME / คงที่)
# =====================================================================
step "2/5 สร้าง Docker Networks"
NETWORKS=(
    "app-internal-${ENV_NAME}"   # ใช้ต่อกันระหว่าง infra ↔ app
    "traefik-public"             # Traefik รับทราฟฟิกเข้า → forward ไป services
    "db-management"              # (สำรอง) สำหรับเครื่องมือจัดการ DB อื่นๆ
)
for net in "${NETWORKS[@]}"; do
    if docker network ls --format '{{.Name}}' | grep -qx "$net"; then
        green "   ✔ Network $net มีอยู่แล้ว"
    else
        echo "   ⏳ สร้าง Network $net ..."
        docker network create --driver=overlay "$net"
        green "   ✔ สร้าง Network $net สำเร็จ"
    fi
done

# =====================================================================
# 4) ตรวจ Traefik Proxy — ตัวกลาง 1 เครื่อง 1 อัน (ไม่ deploy ในสคริปต์นี้)
# =====================================================================
step "3/5 ตรวจ Traefik Proxy (ติดตั้งครั้งเดียวต่อเครื่อง)"
if docker ps --format '{{.Image}}' | grep -qiE '(^|/)traefik[:@]'; then
    green "   ✔ พบ Traefik Proxy รันอยู่ — ใช้ตัวกลางร่วมกับระบบอื่นได้"
else
    yellow "   ⚠️ ยังไม่พบ Traefik Proxy บนเครื่องนี้"
    yellow "   ⚠️ ระบบจะรันภายในได้ แต่จะเข้าเว็บ/API จากภายนอก (พอร์ต 80) ยังไม่ได้"
    echo "      ▶ ติดตั้ง Traefik ครั้งเดียวต่อเครื่อง (1 เครื่อง 1 อัน):  ./setup_traefik.sh"
    echo
fi

# =====================================================================
# 5) รัน Infrastructure (PostgreSQL + Redis)
# =====================================================================
step "4/5 Deploy Infrastructure (PostgreSQL + Redis)"
docker stack deploy -c docker-compose.infra.yml "${ENV_NAME}_infra"
green "   ✔ Stack ${ENV_NAME}_infra ถูก deploy แล้ว"

# รอให้ db / redis ทำงานจริงก่อน build+deploy app (backend จะได้ไม่ crash-loop รอ db)
wait_service() {
    local svc="$1" timeout="${2:-60}"
    echo "   ⏳ รอ $svc ทำงาน (สูงสุด $((timeout * 2)) วิ)..."
    for _ in $(seq 1 "$timeout"); do
        if docker service ps "$svc" --format '{{.CurrentState}}' 2>/dev/null | grep -q '^Running'; then
            green "   ✔ $svc ทำงานแล้ว"
            return 0
        fi
        sleep 2
    done
    yellow "   ⚠️ ยังไม่เห็น $svc รันภายในกำหนด — จะลอง deploy app ต่อ (healthcheck ของ backend คอยรอ db เอง)"
    return 0
}
wait_service "${ENV_NAME}_infra_db" 60
wait_service "${ENV_NAME}_infra_redis" 30

# =====================================================================
# 6) Build Docker Images + Deploy แอป (tag = commit สั้น → rollback ง่าย)
# =====================================================================
step "5/5 Build Docker Images + Deploy แอปพลิเคชัน"
# ใช้เลข Commit 7 ตัวเป็น tag (pull_all.sh/oh_shit.sh ใช้แบบเดียวกัน); ไม่มี git → ใช้ latest
if [ -z "${IMAGE_TAG:-}" ]; then
    if hash=$(git rev-parse --short HEAD 2>/dev/null) && [ -n "$hash" ]; then
        IMAGE_TAG="$hash"
    else
        IMAGE_TAG="latest"
    fi
fi
export IMAGE_TAG
echo "   🏷️  Image tag: $IMAGE_TAG"

BACKEND_IMG="pirivoice-${ENV_NAME}-backend"
FRONTEND_IMG="pirivoice-${ENV_NAME}-frontend"

if [ "$NO_BUILD" = "1" ]; then
    yellow "   ⏭️  (--no-build) ข้าม Build — ใช้ image ที่มีอยู่: ${BACKEND_IMG}:${IMAGE_TAG}, ${FRONTEND_IMG}:${IMAGE_TAG}"
else
    echo "   🔨 Build $BACKEND_IMG ..."
    docker build \
        --build-arg GIT_SHA="${IMAGE_TAG}" \
        -t "${BACKEND_IMG}:${IMAGE_TAG}" ./backend

    echo "   🔨 Build $FRONTEND_IMG (VITE_API_BASE_URL=$VITE_API_BASE_URL) ..."
    # VITE_API_BASE_URL เป็น build-arg → เปลี่ยนค่าแล้ว layer cache หักเอง ไม่ต้อง --no-cache
    docker build \
        --build-arg VITE_API_BASE_URL="${VITE_API_BASE_URL}" \
        -t "${FRONTEND_IMG}:${IMAGE_TAG}" ./frontend
    green "   ✔ Build เสร็จทั้ง 2 image"
fi

echo "   🚀 Deploy stack ${ENV_NAME}_app ..."
docker stack deploy -c docker-compose.app.yml "${ENV_NAME}_app"
green "   ✔ Stack ${ENV_NAME}_app ถูก deploy แล้ว"

# =====================================================================
# 7) สรุปผล
# =====================================================================
echo
green "✅ ============================================================"
green "✅ ระบบพร้อมใช้งานแล้ว!  Environment: ${ENV_NAME}"
green "✅ ============================================================"
echo
echo "   🌐 Web:       ${VITE_API_BASE_URL}"
echo "   🔌 API:       ${API_DOMAIN}"
echo "   🛡️  Proxy:     Traefik ตัวกลาง (1 เครื่อง 1 อัน) — port 80"
echo "   🐘 Infra:     stack ${ENV_NAME}_infra  (PostgreSQL + Redis)"
echo "   📦 App:       stack ${ENV_NAME}_app  (backend ×3 / frontend ×3 / worker ×1)"
echo
echo "   ตรวจสถานะ:   docker stack ps ${ENV_NAME}_app"
echo "   ดู log:       docker service logs -f ${ENV_NAME}_app_backend"
echo
echo "   🔑 Credentials ผู้ดูแลระบบ (สร้างตอนเปิดครั้งแรก):"
echo "      docker service logs ${ENV_NAME}_app_backend | grep 'username'"
echo "      # หรือ cat default_admin_credentials.txt"
echo
echo "   📌 ครั้งถัดไป:"
echo "      ติดตั้ง Traefik (ครั้งเดียวต่อเครื่อง)  →  ./setup_traefik.sh"
echo "      อัปเดตโค้ดใหม่                        →  ./pull_all.sh"
echo "      Rollback ฉุกเฉิน                      →  ./oh_shit.sh"
echo "      Deploy ซ้ำ (ไม่ build)                →  ./setup.sh --no-build"
