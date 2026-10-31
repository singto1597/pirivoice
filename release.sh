#!/bin/bash
#
# release.sh — ตัด release ใหม่ (CHANGELOG → version files → manifest → commit → tag → push → GitHub Release)
#
#   ./release.sh 2.4.0                  # release จริง (refs เดาจาก PR ที่ merge ตั้งแต่ tag ก่อนหน้า)
#   ./release.sh 2.4.0 --dry-run        # ตรวจทุกด่าน แสดง diff แต่ไม่เขียน/ไม่ commit/ไม่ tag/ไม่ push
#   ./release.sh 2.4.0 --refs "PR #112" # ระบุ PR ที่อยู่ในรุ่นนี้เอง (ใช้เมื่อ PR merge ซ้อนเข้า branch)
#   ./release.sh 2.4.0-rc.1             # preview ของ staging (ไม่แตะ CHANGELOG/VERSION, ไม่แย่งป้าย Latest)
#
# กติกา:
#   - CHANGELOG ต้องมีหัวข้อ `## [Unreleased] — <ชื่อรุ่น>` (ห้ามใช้ placeholder)
#     และมีบรรทัด `**Migration:**` ในเนื้อหา
#   - เลขเวอร์ชันเพิ่มทีละขั้นเท่านั้น: 2.3.0 → 2.4.0 (minor) หรือ 2.3.1 (patch)
#     หรือ 3.0.0 (major เมื่อ "วิธีคิดของระบบ" เปลี่ยน)
#   - image tag ของ Docker ยังเป็น commit hash — เลข SemVer อยู่ที่ git tag + CHANGELOG + /api/version
#   - manifest แถวใหม่ใช้ cut=RELEASE (แปลว่า "commit ที่ tag นี้ชี้")
#
# ตัวอย่าง:
#   REFS="PR #111" ./release.sh 2.4.0
#   ./release.sh 2.4.0 --dry-run

set -euo pipefail

cd "$(dirname "$0")"

VERSION=""
REFS="main"
REFS_GIVEN=0
DRY_RUN=0
REPO_SLUG="singto1597/pirivoice"
DATE="$(TZ=Asia/Bangkok date +%Y-%m-%d)"

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
        --refs)    [ $# -ge 2 ] || die "--refs ต้องมีค่า"; REFS="$2"; REFS_GIVEN=1; shift 2 ;;
        -h|--help) usage ;;
        -*)        die "ไม่รู้จักตัวเลือก: $1 (ดู ./release.sh --help)" ;;
        *)         [ -z "$VERSION" ] || die "ระบุเวอร์ชันได้ครั้งเดียว"
                   VERSION="$1"; shift ;;
    esac
done

[ -n "$VERSION" ] || die "ใช้: ./release.sh <X.Y.Z> [--dry-run] [--refs \"PR #N\"]"

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
    die "เลขเวอร์ชันไม่ถูกรูปแบบ SemVer: $VERSION (ตัวอย่าง 2.4.0 หรือ 2.4.0-rc.1)"
fi
IS_RC=0
[[ "$VERSION" == *-* ]] && IS_RC=1

# ---------- 0. ตรวจของก่อนเริ่ม ----------
step "ตรวจสภาพ repo"
if [ "$DRY_RUN" = "0" ]; then
    command -v gh >/dev/null 2>&1 || die "ไม่พบ gh (GitHub CLI)"
fi
command -v node >/dev/null 2>&1 || die "ไม่พบ node (ใช้ตรวจ version manifest)"
command -v npm >/dev/null 2>&1 || die "ไม่พบ npm (ใช้ sync package.json)"

[ "$(git branch --show-current)" = "main" ] || die "ต้องอยู่บน branch main (ปัจจุบัน: $(git branch --show-current))"
[ -z "$(git status --porcelain)" ] || die "working tree ไม่สะอาด — commit หรือ stash ก่อน (dry-run ก็ต้องสะอาด)"

git fetch origin main --quiet
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] \
    || die "main ไม่ตรงกับ origin/main — pull/push ให้ตรงก่อน"
ok "main = origin/main"

if git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null; then
    die "tag v$VERSION มีอยู่แล้ว"
fi

PREV="$(git tag --list 'v*' --sort=-v:refname | head -1)"
[ -n "$PREV" ] || die "ไม่พบ tag ก่อนหน้า — สร้าง tag ย้อนหลังให้ครบก่อน (ดู docs/4-developer-playbook/versioning-and-releases.md)"
ok "tag ก่อนหน้า: $PREV"

# PR ที่ merge เข้ามาตั้งแต่ tag ก่อนหน้า — ดูจากหัว commit ("Merge pull request #N" หรือ "(#N)")
# ใช้เป็นค่าเริ่มต้นของ refs เพื่อไม่ให้ PR ที่ merge แล้วหลุดจากการนับ
# (PR ที่ merge ซ้อนเข้า branch อื่นจะไม่โผล่ใน log ของ main — ระบุเองด้วย --refs ได้)
detect_refs() {
    git log --format=%s "$PREV..HEAD" \
        | grep -oE 'Merge pull request #[0-9]+|\(#[0-9]+\)$' \
        | grep -oE '[0-9]+' | sort -n -u \
        | awk '
            function flush() {
                if (!start) return
                if (out++) printf ","
                printf "PR #%d", start
                if (last > start) printf "-#%d", last
                start = 0
            }
            { if (!start) { start = last = $1; next }
              if ($1 == last + 1) { last = $1; next }
              flush(); start = last = $1 }
            END { flush(); print "" }' \
        || true
}
if [ "$REFS_GIVEN" = "0" ]; then
    DETECTED="$(detect_refs)"
    if [ -n "$DETECTED" ]; then
        REFS="$DETECTED"
        ok "ตรวจพบ PR ในรุ่นนี้: $REFS"
    fi
fi

# ---------- 1. ตรวจว่าเลขเดินหน้าถูกขั้น ----------
CURRENT="$(tr -d '[:space:]' < VERSION)"
[ "$CURRENT" = "${PREV#v}" ] || die "VERSION ในไฟล์ ($CURRENT) ไม่ตรงกับ tag ล่าสุด ($PREV)"

if [ "$IS_RC" = "0" ]; then
    IFS=. read -r MA MI PA <<< "$VERSION"
    IFS=. read -r PMA PMI PPA <<< "${PREV#v}"
    if [ "$MA" -eq $((PMA + 1)) ] && [ "$MI" -eq 0 ] && [ "$PA" -eq 0 ]; then
        BUMP=major
    elif [ "$MA" -eq "$PMA" ] && [ "$MI" -eq $((PMI + 1)) ] && [ "$PA" -eq 0 ]; then
        BUMP=minor
    elif [ "$MA" -eq "$PMA" ] && [ "$MI" -eq "$PMI" ] && [ "$PA" -eq $((PPA + 1)) ]; then
        BUMP=patch
    else
        die "เลขเวอร์ชันต้องเดินทีละขั้นจาก $PREV: minor = x.$((PMI + 1)).0, patch = x.y.$((PPA + 1)), major = $((PMA + 1)).0.0"
    fi
    ok "เวอร์ชัน $VERSION (bump=$BUMP)"
else
    BUMP=""
    ok "เวอร์ชัน $VERSION (rc — ไม่แตะ CHANGELOG/VERSION)"
fi

# ---------- 2. ตรวจ manifest ของประวัติเดิม ----------
step "ตรวจ version manifest"
node scripts/version-manifest.mjs

# ---------- 3. เตรียม notes + ตัด CHANGELOG ----------
NOTES="$(mktemp)"
BACKUP_DIR=""
COMMITTED=0
VERSION_FILES="CHANGELOG.md VERSION backend/core/config.py frontend/package.json frontend/package-lock.json scripts/version-manifest.tsv"
# สำรองก่อนแตะอะไรทั้งสิ้น — ล้มกลางทาง (เช่น preflight ไม่ผ่าน) ต้องคืนไฟล์เดิม
if [ "$IS_RC" = "0" ]; then
    BACKUP_DIR="$(mktemp -d)"
    for f in $VERSION_FILES; do
        mkdir -p "$BACKUP_DIR/$(dirname "$f")"
        cp "$f" "$BACKUP_DIR/$f"
    done
fi
cleanup() {
    rm -f "$NOTES"
    if [ -n "$BACKUP_DIR" ]; then
        if [ "$COMMITTED" = "0" ]; then
            for f in $VERSION_FILES; do
                cp "$BACKUP_DIR/$f" "$f" 2>/dev/null || true
            done
            echo "↩ คืนไฟล์เวอร์ชันเดิมแล้ว (ยังไม่มีการ commit)" >&2
        fi
        rm -rf "$BACKUP_DIR"
    fi
}
trap cleanup EXIT

TITLE="$(
    python3 - "$VERSION" "$DATE" "$PREV" "$REPO_SLUG" "$NOTES" "$IS_RC" <<'PY'
import re
import sys

version, date, prev, slug, notes_path, is_rc = sys.argv[1:7]
is_rc = is_rc == "1"
path = "CHANGELOG.md"
text = open(path, encoding="utf-8").read()

m = re.search(
    r"^## \[Unreleased\](?:[ \t]*—[ \t]*([^\n]*))?[ \t]*\n(.*?)(?=^## \[)",
    text,
    re.M | re.S,
)
if not m:
    sys.exit("ไม่พบหัวข้อ '## [Unreleased] — <ชื่อรุ่น>' ใน CHANGELOG.md")

title = (m.group(1) or "").strip()
body = m.group(2).strip()

if not title or title == "ยังไม่ตัดเวอร์ชัน":
    sys.exit("หัวข้อ [Unreleased] ยังไม่มีชื่อรุ่น — เขียน '## [Unreleased] — <ชื่อรุ่น>' ก่อน")
if not body:
    sys.exit("section [Unreleased] ว่าง — ยังไม่มีอะไรให้ปล่อย")
if "**Migration:**" not in body:
    sys.exit("section [Unreleased] ไม่มีบรรทัด **Migration:**")

notes = f"## v{version} — {date} — {title}\n\n{body}\n"
open(notes_path, "w", encoding="utf-8").write(notes)

if is_rc:
    # rc = ป้าย preview ของโค้ดปัจจุบัน ไม่แก้ CHANGELOG และไม่เลื่อนเลขเวอร์ชัน
    print(title)
    sys.exit(0)

new_section = (
    "## [Unreleased] — ยังไม่ตัดเวอร์ชัน\n\n"
    f"## [{version}] — {date} — {title}\n\n"
    + body
    + "\n\n"
)
new = text[: m.start()] + new_section + text[m.end():]

old_link = f"[Unreleased]: https://github.com/{slug}/compare/{prev}...HEAD"
new_link = (
    f"[Unreleased]: https://github.com/{slug}/compare/v{version}...HEAD\n"
    f"[{version}]: https://github.com/{slug}/compare/{prev}...v{version}"
)
if old_link not in new:
    sys.exit(f"ไม่พบ compare link ของ [Unreleased] ที่ชี้ {prev} — ตรวจท้าย CHANGELOG.md")
new = new.replace(old_link, new_link, 1)

open(path, "w", encoding="utf-8").write(new)
print(title)
PY
)"

[ -n "$TITLE" ] || die "อ่านชื่อรุ่นจาก CHANGELOG ไม่ได้"
[ -s "$NOTES" ] || die "notes จาก CHANGELOG ว่าง — ห้าม tag"
ok "ชื่อรุ่น: $TITLE"

# ---------- 4. sync เลขเวอร์ชัน + manifest ----------
if [ "$IS_RC" = "0" ]; then
    step "sync เลขเวอร์ชันเป็น $VERSION"
    echo "$VERSION" > VERSION

    python3 - "$VERSION" <<'PY'
import re
import sys

version = sys.argv[1]
path = "backend/core/config.py"
src = open(path, encoding="utf-8").read()
new, n = re.subn(r'PROJECT_VERSION: str = "[^"]*"', f'PROJECT_VERSION: str = "{version}"', src, count=1)
if n != 1:
    sys.exit("ไม่พบ PROJECT_VERSION ใน backend/core/config.py")
open(path, "w", encoding="utf-8").write(new)
PY

    ( cd frontend && npm version "$VERSION" --no-git-tag-version --allow-same-version >/dev/null )
    ok "VERSION · config.py · package.json · package-lock.json = $VERSION"

    printf '%s\t%s\tRELEASE\t%s\t%s\t%s\n' \
        "$VERSION" "$DATE" "$BUMP" "$TITLE" "$REFS" >> scripts/version-manifest.tsv
    ok "เพิ่มแถว manifest: $VERSION ($BUMP) refs=$REFS"

    # ตรวจซ้ำก่อนแตะ git — ถ้า refs ไม่ครบ (เช่น PR ที่ merge แล้วแต่ไม่ได้นับ)
    # ต้องล้มตรงนี้ ไม่ใช่หลังสร้าง tag แล้ว
    step "preflight — manifest จะผ่านหลังสร้าง tag หรือไม่"
    node scripts/version-manifest.mjs --preflight
fi

# ---------- 5. dry-run: แสดง diff แล้วคืนไฟล์ ----------
if [ "$DRY_RUN" = "1" ]; then
    step "dry-run — diff ที่จะถูก commit"
    git --no-pager diff --stat
    echo
    echo "notes ที่จะใช้ใน GitHub Release (ต้นฉบับ):"
    sed 's/^/  /' "$NOTES" | head -20
    echo
    if [ -n "$BACKUP_DIR" ]; then
        for f in $VERSION_FILES; do cp "$BACKUP_DIR/$f" "$f"; done
        rm -rf "$BACKUP_DIR"
        BACKUP_DIR=""
    fi
    if [ -n "$(git status --porcelain)" ]; then
        die "dry-run คืนไฟล์ไม่ครบ — ตรวจ git status ก่อนทำจริง"
    fi
    ok "dry-run ผ่านทุกด่าน — ไม่มีการเขียน/commit/tag/push"
    exit 0
fi

# ---------- 6. commit + tag + push ----------
step "commit และ tag"
if [ -n "$(git status --porcelain)" ]; then
    git add CHANGELOG.md VERSION backend/core/config.py frontend/package.json frontend/package-lock.json
    if [ "$IS_RC" = "0" ]; then git add scripts/version-manifest.tsv; fi
    git commit -m "chore(release): v$VERSION"
    ok "commit chore(release): v$VERSION"
else
    ok "ไฟล์เวอร์ชันตรงอยู่แล้ว — ไม่ต้อง commit ใหม่"
fi
# ผ่านจุดนี้แล้วห้ามคืนไฟล์ — commit อยู่ในประวัติแล้ว
COMMITTED=1

git tag -a "v$VERSION" -m "v$VERSION — $DATE — $TITLE"
ok "annotated tag v$VERSION"

if [ "$IS_RC" = "0" ]; then
    # ตรวจซ้ำหลัง tag: แถว RELEASE จะ resolve ผ่าน tag นี้
    node scripts/version-manifest.mjs
fi

step "push main + tag"
git push origin main
git push origin "v$VERSION"
ok "push แล้ว"

# ---------- 7. GitHub Release ----------
step "สร้าง GitHub Release"
if [ "$IS_RC" = "1" ]; then
    gh release create "v$VERSION" \
        --verify-tag --prerelease \
        --title "v$VERSION" \
        --notes-file "$NOTES"
else
    gh release create "v$VERSION" \
        --verify-tag --latest \
        --title "v$VERSION" \
        --notes-file "$NOTES"
fi

ok "ปล่อย v$VERSION เสร็จ — ต่อไป deploy staging/production ตามปกติ (pull_all.sh)"
