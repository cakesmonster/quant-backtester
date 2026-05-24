#!/bin/bash
# quant-backtester 公网开关
# 用法: bash toggle-public.sh         → 切换（开↔关）
#       bash toggle-public.sh on      → 开放 0.0.0.0
#       bash toggle-public.sh off     → 关闭 127.0.0.1
set -e

SVC="/etc/systemd/system/quant-backtester.service"
current=$(grep '\-\-host' "$SVC" | sed 's/.*--host \([^ ]*\).*/\1/')

case "${1:-toggle}" in
  on|open)     new="0.0.0.0";   label="🟢 开放 0.0.0.0" ;;
  off|close)    new="127.0.0.1"; label="🔒 关闭 127.0.0.1" ;;
  toggle)
    if [ "$current" = "0.0.0.0" ]; then
      new="127.0.0.1"; label="🔒 关闭 127.0.0.1"
    else
      new="0.0.0.0";   label="🟢 开放 0.0.0.0"
    fi
    ;;
esac

if [ "$current" = "$new" ]; then
  echo "已是 $current，无需切换"
  exit 0
fi

sed -i "s/--host [^ ]*/--host $new/" "$SVC"
systemctl daemon-reload
systemctl restart quant-backtester

# 等就绪
for i in $(seq 1 10); do
  if curl -s http://127.0.0.1:8100/api/health > /dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "监听: $(ss -tlnp 2>/dev/null | grep 8100 || echo '端口 8100')"
echo "$label — 完成"
