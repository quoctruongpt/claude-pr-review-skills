#!/usr/bin/env bash
# Cài bộ review PR cho Claude Code vào ~/.claude (hoặc $CLAUDE_CONFIG_DIR).
# Dùng: ./install.sh [--no-cli] [--no-claude-md]
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
INSTALL_CLI=1
INSTALL_CLAUDE_MD=1
for arg in "$@"; do
  case "$arg" in
    --no-cli) INSTALL_CLI=0 ;;
    --no-claude-md) INSTALL_CLAUDE_MD=0 ;;
    -h|--help) sed -n 2,3p "$0"; exit 0 ;;
    *) echo "Tham số lạ: $arg" >&2; exit 2 ;;
  esac
done

echo "→ Cài vào $DEST"
mkdir -p "$DEST/skills" "$DEST/agents"

# 1. Skills và agent (ghi đè bản cũ cùng tên)
for s in pr-review-expert diff-scoped-review; do
  rm -rf "$DEST/skills/$s"
  cp -R "$SRC/skills/$s" "$DEST/skills/$s"
  echo "  ✓ skill $s"
done
cp "$SRC/agents/breaker.md" "$DEST/agents/breaker.md"
echo "  ✓ agent breaker"

# 2. Mục "Review code" trong CLAUDE.md (thay khối cũ giữa marker nếu có)
if [ "$INSTALL_CLAUDE_MD" = 1 ]; then
  python3 - "$DEST/CLAUDE.md" "$SRC/claude-md/review-code.md" <<'PY'
import os, re, sys
target, snippet = sys.argv[1], open(sys.argv[2]).read()
text = open(target).read() if os.path.exists(target) else ""
pat = re.compile(r"<!-- PR_REVIEW_START -->.*?<!-- PR_REVIEW_END -->\n?", re.S)
if pat.search(text):
    text = pat.sub(lambda _: snippet, text)
else:
    text = (text.rstrip() + "\n\n" if text.strip() else "") + snippet
open(target, "w").write(text)
PY
  echo "  ✓ CLAUDE.md: mục Review code"
fi

# 3. CLI: srcwalk (điều hướng code), ocr (chia file cho reviewer) + skill srcwalk
if [ "$INSTALL_CLI" = 1 ]; then
  if command -v npm >/dev/null; then
    npm install -g srcwalk @alibaba-group/open-code-review >/dev/null
    echo "  ✓ CLI srcwalk $(srcwalk --version 2>/dev/null | awk '{print $2}'), ocr $(ocr --version 2>/dev/null | head -1 | awk '{print $2}')"
  else
    echo "  ! Không có npm: tự cài 'srcwalk' và '@alibaba-group/open-code-review'"
  fi
  mkdir -p "$DEST/skills/srcwalk"
  base=https://raw.githubusercontent.com/sting8k/srcwalk/main/skills/srcwalk
  if curl -fsSL "$base/SKILL.md" -o "$DEST/skills/srcwalk/SKILL.md" && curl -fsSL "$base/GUIDE.md" -o "$DEST/skills/srcwalk/GUIDE.md"; then
    echo "  ✓ skill srcwalk"
  else
    echo "  ! Không tải được skill srcwalk (bỏ qua, CLI vẫn dùng được)"
  fi
fi

# 4. Kiểm tra công cụ phụ thuộc
echo "→ Kiểm tra phụ thuộc"
for c in git gh python3 jq codex srcwalk ocr; do
  if command -v "$c" >/dev/null; then echo "  ✓ $c"; else echo "  ✗ $c (thiếu)"; fi
done
# Claude Code tự kèm rg trong shell của nó; chỉ cần cài khi chạy lệnh ngoài Claude
command -v rg >/dev/null && echo "  ✓ rg" || echo "  ~ rg: Claude Code có sẵn; muốn dùng ngoài Claude thì 'brew install ripgrep'"
python3 "$DEST/skills/diff-scoped-review/scripts/diff_risk_router.py" --sample >/dev/null && echo "  ✓ script router chạy được"

echo "Xong. Mở phiên Claude Code mới rồi gõ: review PR #<số>"
