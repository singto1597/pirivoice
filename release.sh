#!/bin/bash
#
# release.sh — ตัด release ใหม่ (CHANGELOG → version files → commit → tag → push → GitHub Release)
#
#   ./release.sh 2.3.0          # release จริง
#   ./release.sh 2.4.0-rc.1     # preview ของ staging (ไม่แตะ CHANGELOG, ไม่แย่งป้าย Latest)
#
# ⚠️ สคริปต์นี้ **ไม่แก้ IMAGE_TAG ของ Docker** — image ยังติด tag ด้วย commit hash
#    ตามเดิม (pull_all.sh / oh_shit.sh) เลข SemVer อยู่ที่ git tag + CHANGELOG + /api/version
#
# ⚠️ commit ที่สคริปต์สร้างเปลี่ยนแค่ CHANGELOG/VERSION ⇒ `./oh_shit.sh` (reset --hard HEAD~1)
#    จะย้อนไปที่ commit ก่อนหน้าซึ่งโค้ดเหมือนกันทุกไบต์ — ดูเอกสาร versioning-and-releases.md

set -euo pipefail

VERSION="${1:-}"
REPO_SLUG="singto1597/pirivoice"
DATE="$(TZ=Asia/Bangkok date +%Y-%m-%d)"

die() { echo "❌ $*" >&2; exit 1; }
ok()  { echo "✅ $*"; }

# ---------- 0. ตรวจของก่อนเริ่ม ----------
[ -n "$VERSION" ] || die "ใช้: ./release.sh <X.Y.Z>"

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
    die "เลขเวอร์ชันไม่ถูกรูปแบบ SemVer: $VERSION (ตัวอย่าง 2.3.0 หรือ 2.4.0-rc.1)"
fi

command -v gh >/dev/null 2>&1 || die "ไม่พบ gh (GitHub CLI)"

[ "$(git branch --show-current)" = "main" ] || die "ต้องอยู่บน branch main (ปัจจุบัน: $(git branch --show-current))"
[ -z "$(git status --porcelain)" ] || die "working tree ไม่สะอาด — commit หรือ stash ก่อน"

echo "⬇️  ตรวจว่า main ตรงกับ origin..."
git fetch origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] && ok "main = origin/main" \
    || die "main ไม่ตรงกับ origin/main — pull/push ให้ตรงก่อน"

if git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null; then
    die "tag v$VERSION มีอยู่แล้ว"
fi

PREV="$(git tag --list 'v*' --sort=-v:refname | head -1)"
[ -n "$PREV" ] || die "ไม่พบ tag ก่อนหน้า — สร้าง tag ย้อนหลังให้ครบก่อน (ดู docs/4-developer-playbook/versioning-and-releases.md)"
ok "tag ก่อนหน้า: $PREV"

NOTES="$(mktemp)"
trap 'rm -f "$NOTES"' EXIT

# ---------- 1. CHANGELOG ----------
echo "📝 ตัด CHANGELOG [Unreleased] → [$VERSION]..."
python3 - "$VERSION" "$DATE" "$PREV" "$REPO_SLUG" "$NOTES" <<'PY'
import re
import sys

version, date, prev, slug, notes_path = sys.argv[1:6]
path = "CHANGELOG.md"
text = open(path, encoding="utf-8").read()

m = re.search(r"^## \[Unreleased\]\s*\n(.*?)(?=^## \[)", text, re.M | re.S)
if not m:
    sys.exit("ไม่พบหัว '## [Unreleased]' ใน CHANGELOG.md")

body = m.group(1).strip()
if "- " not in body:
    sys.exit("section [Unreleased] ว่าง — ยังไม่มีอะไรให้ปล่อย")

if "-" in version:
    # rc = preview ของชุดเดิม → ไม่แตะ CHANGELOG และไม่สร้าง compare link
    open(notes_path, "w", encoding="utf-8").write(f"## v{version} — {date}\n\n{body}\n")
    sys.exit(0)

new = (
    text[: m.start()]
    + "## [Unreleased]\n\n"
    + f"## [{version}] - {date}\n"
    + body
    + "\n\n"
    + text[m.end() :]
)

# `prev` เป็น tag เต็มอยู่แล้ว (v2.2.0) — อย่าเติม v ซ้ำ
old_link = f"[Unreleased]: https://github.com/{slug}/compare/{prev}...HEAD"
new_link = (
    f"[Unreleased]: https://github.com/{slug}/compare/v{version}...HEAD\n"
    f"[{version}]: https://github.com/{slug}/compare/{prev}...v{version}"
)
if old_link not in new:
    sys.exit(f"ไม่พบ compare link ของ [Unreleased] ที่ชี้ {prev} — ตรวจท้าย CHANGELOG.md")
new = new.replace(old_link, new_link, 1)

open(path, "w", encoding="utf-8").write(new)
open(notes_path, "w", encoding="utf-8").write(f"## v{version} — {date}\n\n{body}\n")
PY

# ---------- 2. sync เลขเวอร์ชันทุกไฟล์ ----------
echo "🔢 sync เลขเวอร์ชันเป็น $VERSION..."
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

# npm version อัปเดตทั้ง package.json และ package-lock.json (version + packages[""].version)
( cd frontend && npm version "$VERSION" --no-git-tag-version --allow-same-version >/dev/null )
ok "VERSION · config.py · package.json · package-lock.json = $VERSION"

# ---------- 3. commit (ถ้ามีอะไรเปลี่ยน) ----------
if [ -n "$(git status --porcelain)" ]; then
    git add CHANGELOG.md VERSION backend/core/config.py frontend/package.json frontend/package-lock.json
    git commit -m "chore(release): v$VERSION"
    ok "commit chore(release): v$VERSION"
else
    ok "ไฟล์เวอร์ชันตรงอยู่แล้ว — ไม่ต้อง commit ใหม่"
fi

# ---------- 4. tag + push ----------
echo "🏷️  สร้าง annotated tag v$VERSION..."
git tag -a "v$VERSION" -m "v$VERSION — $DATE"
git push origin main
git push origin "v$VERSION"
ok "push main และ tag v$VERSION แล้ว"

# ---------- 5. GitHub Release ----------
echo "🚀 สร้าง GitHub Release..."
if [[ "$VERSION" == *-* ]]; then
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
