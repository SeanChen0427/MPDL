#!/bin/zsh
cd -- "${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export TUBEDROP_OPEN=1
python3 server.py
printf '\n工具已停止。按 Enter 關閉。\n'
read
