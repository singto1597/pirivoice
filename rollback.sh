#!/bin/bash
#
# rollback.sh — สลับ stack กลับไป image ชุดก่อน โดยไม่แตะ git เลย
#
#   ./rollback.sh --list                 # ดู image tag ที่มีอยู่ในเครื่อง (ใหม่ → เก่า)
#   ./rollback.sh <image-tag> --dry-run  # ตรวจว่า image มีจริง จะสลับอะไรบ้าง (ไม่ deploy)
#   ./rollback.sh <image-tag>            # สลับจริง (ถามยืนยันก่อน)
#   ./rollback.sh <image-tag> --yes      # สลับจริงโดยไม่ถาม (ใช้ใน automate)
#
# <image-tag> คือ commit hash ที่ใช้ tag image ตอน deploy (เช่น 9fbe3ad หรือ hash เต็ม)
# สคริปต์นี้ไม่แก้ git — checkout ยังอยู่ที่เดิม ครั้งต่อไปที่รัน pull_all.sh จะ deploy HEAD ตามปกติ
#
# ทำอะไร:
#   1. โหลด .env → ENV_NAME
#   2. ตรวจว่า image ของ backend/frontend tag นี้มีอยู่ในเครื่อง
#   3. แสดง image ที่รันอยู่ตอนนี้ vs ที่จะสลับไป
#   4. docker stack deploy ด้วย IMAGE_TAG=<tag> (worker/push_worker ใช้ image backend ตามไปด้วย)

set -euo pipefail

cd "$(dirname "$0")"

TAG=""
DRY_RUN=0
ASSUME_YES=0
LIST=0

die() { echo "❌ $*" >&2; exit 1; }
ok()  { echo "✅ $*"; }
step() { echo; echo "▶ $*"; }

usage() {
    awk 'NR >= 2 && /^#/ { sub(/^# ?/, ""); print; next } NR >= 2 { exit }' "$0"
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --yes|-y)  ASSUME_YES=1; shift ;;
        --list)    LIST=1; shift ;;
        -h|--help) usage ;;
        -*)        die "ไม่รู้จักตัวเลือก: $1 (ดู ./rollback.sh --help)" ;;
        *)         [ -z "$TAG" ] || die "ระบุ image tag ได้ครั้งเดียว"
                   TAG="$1"; shift ;;
    esac
done

command -v docker >/dev/null 2>&1 || die "ไม่พบ docker"

[ -f .env ] || die "ไม่พบไฟล์ .env (ต้องมี ENV_NAME)"
set -a
. ./.env
set +a
[ -n "${ENV_NAME:-}" ] || die ".env ไม่มี ENV_NAME"

BACKEND_IMAGE="pirivoice-${ENV_NAME}-backend"
FRONTEND_IMAGE="pirivoice-${ENV_NAME}-frontend"
STACK="${ENV_NAME}_app"

if [ "$LIST" = "1" ]; then
    step "image tag ที่มีในเครื่อง ($ENV_NAME)"
    for img in "$BACKEND_IMAGE" "$FRONTEND_IMAGE"; do
        echo "$img:"
        docker image ls "$img" --format '  {{.Tag}}\t{{.CreatedAt}}' \
            | grep -v '^  <none>' | sort -k2,3 -r | head -15 | sed 's/\t/  /'
    done
    echo
    echo "ใช้: ./rollback.sh <tag> --dry-run"
    exit 0
fi

[ -n "$TAG" ] || die "ใช้: ./rollback.sh <image-tag> [--dry-run|--yes]  หรือ ./rollback.sh --list"

# tag ของ image คือ commit hash — รับเฉพาะ hex 7–40 ตัว กันการชี้ไป image อื่นโดยไม่ตั้งใจ
[[ "$TAG" =~ ^[0-9a-f]{7,40}$ ]] || die "image tag ต้องเป็น commit hash 7–40 ตัวพิมพ์เล็ก (พบ: $TAG)"

step "ตรวจ image $TAG"
for img in "$BACKEND_IMAGE" "$FRONTEND_IMAGE"; do
    docker image inspect "$img:$TAG" >/dev/null 2>&1 \
        || die "ไม่พบ image $img:$TAG — tag นี้ไม่เคย build บนเครื่องนี้ (ดูรายการด้วย ./rollback.sh --list)"
    ok "$img:$TAG"
done

current_image() {
    docker service inspect "${STACK}_$1" --format '{{.Spec.TaskTemplate.ContainerSpec.Image}}' 2>/dev/null || echo "(ไม่พบ service)"
}

step "จะสลับ stack ${STACK}"
echo "  backend  : $(current_image backend)"
echo "          → ${BACKEND_IMAGE}:${TAG}"
echo "  frontend : $(current_image frontend)"
echo "          → ${FRONTEND_IMAGE}:${TAG}"
echo "  worker / push_worker ใช้ image backend ตามไปด้วย"

if [ "$DRY_RUN" = "1" ]; then
    echo
    ok "dry-run — image มีครบ ไม่ได้ deploy อะไร"
    exit 0
fi

echo
echo "⚠️  หลังสลับแล้ว checkout ของ git จะยังอยู่ที่เดิม (ไม่ตรงกับ image ที่รัน)"
echo "    รัน pull_all.sh ครั้งถัดไปจะ deploy HEAD กลับมา — rollback นี้เป็นเรื่องชั่วคราว"
if [ "$ASSUME_YES" = "0" ]; then
    read -r -p "พิมพ์ 'rollback' เพื่อยืนยัน: " ans
    [ "$ans" = "rollback" ] || die "ยกเลิก — ไม่ได้แตะอะไร"
fi

step "deploy ${STACK} ด้วย IMAGE_TAG=$TAG"
export IMAGE_TAG="$TAG"
docker stack deploy -c docker-compose.app.yml "$STACK"

step "ตรวจหลัง deploy"
for svc in backend frontend worker push_worker; do
    running="$(current_image "$svc")"
    # docker service inspect คืนชื่อ image พร้อม digest ต่อท้าย (repo:tag@sha256:...) — เทียบด้วย tag
    if [[ "$running" == *":$TAG"* ]]; then
        ok "$svc → $running"
    else
        echo "  ? $svc → ${running:-ไม่พบ service}  (ตรวจด้วย docker service ps ${STACK}_$svc)"
    fi
done

ok "rollback ไป $TAG เสร็จ — ถ้าจะกลับเวอร์ชันล่าสุด ให้รัน ./pull_all.sh"
