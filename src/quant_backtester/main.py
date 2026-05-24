"""
quant-backtester — FastAPI 入口

端点:
  GET  /                 → 看板页面
  GET  /api/health       → 服务存活
  GET  /api/strategies   → 可用策略列表
  GET  /api/stock-pool   → 股票池统计
  GET  /api/cache-stats  → 缓存统计
  POST /api/backtest     → 执行回测
"""

import os
import time
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from quant_backtester.config import FASTAPI_HOST, FASTAPI_PORT
from quant_backtester.data.cache import cache_stats
from quant_backtester.data.stock_pool import pool_stats, random_sample
from quant_backtester.engine.backtest import run_one
from quant_backtester.engine.metrics import compute_metrics, aggregate_metrics
from quant_backtester.strategies.registry import discover_strategies

app = FastAPI(
    title="Quant Backtester",
    description="A股量化回测框架 — 通达信K线 + 策略插件",
    version="0.2.0",
)

# 启动时发现所有策略
STRATEGIES = discover_strategies()


class BacktestRequest(BaseModel):
    strategy: str = Field(..., description="策略名称")
    stock_count: int = Field(default=10, ge=1, le=100, description="随机股票数")
    window_days: int = Field(default=180, ge=60, le=500, description="回测窗口(天)")
    runs_per_stock: int = Field(default=3, ge=1, le=10, description="每只重复次数")
    initial_capital: float = Field(default=100_000, ge=10_000, description="初始资金")


# ── 页面 ──

@app.get("/", response_class=HTMLResponse)
def index():
    """看板页面。"""
    template_path = os.path.join(
        os.path.dirname(__file__), "dashboard", "templates", "index.html"
    )
    with open(template_path, encoding="utf-8") as f:
        return f.read()


# ── API ──

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.2.0"}


@app.get("/api/strategies")
def api_strategies():
    """可用策略列表 + 描述。"""
    return {
        "strategies": sorted(STRATEGIES.keys()),
        "details": {
            name: {"name": name, "description": cls.description}
            for name, cls in STRATEGIES.items()
        },
    }


@app.get("/api/stock-pool")
def api_stock_pool():
    return pool_stats()


@app.get("/api/cache-stats")
def api_cache_stats():
    return cache_stats()


@app.post("/api/backtest")
def api_backtest(req: BacktestRequest):
    """执行回测并返回结果。"""
    if req.strategy not in STRATEGIES:
        return {"error": f"策略 '{req.strategy}' 不存在，可用: {sorted(STRATEGIES.keys())}"}

    strategy_cls = STRATEGIES[req.strategy]
    codes = random_sample(req.stock_count)

    t0 = time.time()
    results: list[dict[str, Any]] = []

    for idx, code in enumerate(codes):
        for run_idx in range(req.runs_per_stock):
            seed = run_idx * 1000 + idx
            r = run_one(
                code=code,
                strategy_cls=strategy_cls,
                window_days=req.window_days,
                initial_capital=req.initial_capital,
                seed=seed,
            )
            if r["success"]:
                m = compute_metrics(
                    r["equity_curve"],
                    r["trades"],
                    r["initial_capital"],
                    r["window_days"],
                )
                r["metrics"] = m
            results.append(r)

    elapsed = round(time.time() - t0, 1)
    agg = aggregate_metrics(results)

    return {
        "strategy": req.strategy,
        "params": req.model_dump(),
        "elapsed_seconds": elapsed,
        "results": results,
        "aggregate": agg,
    }


# ── CLI 入口 ──
def main():
    import uvicorn
    uvicorn.run("quant_backtester.main:app", host=FASTAPI_HOST, port=FASTAPI_PORT, log_level="info")


if __name__ == "__main__":
    main()
