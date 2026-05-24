#!/bin/bash
# 公网开关 — 切换日晷绑定地址
# 用法: ./toggle-public.sh [on|off]

ACTION="${1:-status}"
SERVICE="sundial.service"
ENV_FILE="/etc/systemd/system/sundial.service.d/env.conf"

case "$ACTION" in
    on)
        echo "🔓 开放公网访问 (0.0.0.0:8200)"
        mkdir -p "$(dirname "$ENV_FILE")"
        cat > "$ENV_FILE" <<EOF
[Service]
Environment=SUNDIAL_HOST=0.0.0.0
EOF
        systemctl daemon-reload
        systemctl restart "$SERVICE"
        echo "已开放 — 确保防火墙放行 8200 端口"
        ;;
    off)
        echo "🔒 关闭公网访问 (127.0.0.1:8200)"
        rm -f "$ENV_FILE"
        systemctl daemon-reload
        systemctl restart "$SERVICE"
        echo "已关闭 — 仅本地可访问"
        ;;
    status)
        if [ -f "$ENV_FILE" ] && grep -q "0.0.0.0" "$ENV_FILE" 2>/dev/null; then
            echo "🔓 当前: 公网 (0.0.0.0:8200)"
        else
            echo "🔒 当前: 本地 (127.0.0.1:8200)"
        fi
        ;;
    *)
        echo "用法: $0 [on|off|status]"
        exit 1
        ;;
esac
