#!/bin/bash
# 热榜快照脚本 — cron 每小时调用
# 用法: ./hot_rank_snapshot.sh [1130|1500|2100]
SLOT="${1:-$(date +%H%M)}"
cd /root/.hermes/projects/sundial
python3 -m sundial.services.hot_rank "$SLOT"
