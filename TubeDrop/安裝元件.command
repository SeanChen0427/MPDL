#!/bin/zsh
set -e
cd -- "${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

PYTHON_BIN=''
for candidate in "${TUBEDROP_PYTHON:-}" "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3" python3.12 python3.11 python3.10 python3; do
  if [[ -n "$candidate" ]] && command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v "$candidate")"
    break
  fi
done
NODE_BIN="$(command -v node || true)"
if [[ -z "$NODE_BIN" ]]; then
  nodes=("$HOME"/.nvm/versions/node/*/bin/node(N))
  if (( ${#nodes} )); then NODE_BIN="${nodes[-1]}"; fi
fi
if [[ -z "$PYTHON_BIN" ]] || ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1 || [[ -z "$NODE_BIN" ]]; then
  print '請先安裝 Python 3.10 以上、FFmpeg 與 Node.js。'
  print '若已安裝 Homebrew，可在終端機執行：brew install python@3.12 ffmpeg node'
  print '完成後再重新開啟這個安裝程式。'
  exit 1
fi

VERSION='2026.08.19'
EXPECTED='1fa6733c37ea6fb51c99ad8fe785e7b7e5f3246c9b980230329d4fb72ed8d4d6'
TARGET='bin/yt-dlp'
mkdir -p bin
if [[ -f "$TARGET" ]] && "$PYTHON_BIN" -c 'import hashlib, pathlib, sys; sys.exit(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest() != sys.argv[2])' "$TARGET" "$EXPECTED"; then
  print "yt-dlp $VERSION 已就緒，校驗通過。"
else
  TEMP_FILE="$(mktemp "${TMPDIR:-/tmp}/tubedrop-yt-dlp.XXXXXX")"
  trap 'rm -f -- "$TEMP_FILE"' EXIT
  print "正在下載官方 yt-dlp $VERSION…"
  curl --fail --location --retry 2 --connect-timeout 15 --max-time 180 --output "$TEMP_FILE" "https://github.com/yt-dlp/yt-dlp/releases/download/$VERSION/yt-dlp"
  "$PYTHON_BIN" - "$TEMP_FILE" "$TARGET" "$EXPECTED" <<'PY'
import hashlib
from pathlib import Path
import os
import sys
source, target, expected = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
    sys.exit('下載檔案校驗不符，未安裝。請重試或檢查官方版本。')
os.replace(source, target)
PY
fi
print "Python：$PYTHON_BIN"
print '元件準備完成，請雙擊「啟動.command」開始使用。'
