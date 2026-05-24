"""
quant-backtester — FastAPI 入口

P0 阶段暴露的端点:
  GET  /                 → 占位首页
  GET  /api/health       → 服务存活
  GET  /api/stock-pool   → 股票池统计
  GET  /api/cache-stats  → 缓存统计
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from quant_backtester.config import FASTAPI_HOST, FASTAPI_PORT
from quant_backtester.data.cache import cache_stats
from quant_backtester.data.stock_pool import pool_stats

app = FastAPI(
    title="Quant Backtester",
    description="A股量化回测框架 — 通达信K线 + 策略插件",
    version="0.1.0",
)


@app.get("/", response_class=HTMLResponse)
def index():
    """占位首页，后续替换为看板。"""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Quant Backtester</title></head>
    <body style="font-family: sans-serif; padding: 40px;">
      <h1>🔬 Quant Backtester v0.1</h1>
      <p>P0 — 数据层已就绪</p>
      <ul>
        <li><a href="/api/health">/api/health</a></li>
        <li><a href="/api/stock-pool">/api/stock-pool</a></li>
        <li><a href="/api/cache-stats">/api/cache-stats</a></li>
        <li><a href="/docs">/docs (Swagger)</a></li>
      </ul>
      <p style="margin-top: 30px; color: #888; font-size: 14px;">
        看板页面将在 P3 阶段开发
      </p>
    </body>
    </html>
    """


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/stock-pool")
def api_stock_pool():
    """股票池统计 — 总数、最后更新时间。"""
    return pool_stats()


@app.get("/api/cache-stats")
def api_cache_stats():
    """缓存统计 — 已缓存股票数、总大小。"""
    return cache_stats()


# ── CLI 入口 ───────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=FASTAPI_HOST, port=FASTAPI_PORT, log_level="info")
