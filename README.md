# 🔬 Quant Backtester

A股量化回测框架 — 通达信历史K线 + 自定义策略插件 + FastAPI 看板。

```
uv pip install -e .         # 安装
quant-backtester            # 启动 → http://localhost:8100
```

---

## 架构

```
浏览器 (IP:8100)                    数据流
    │                                 │
    ▼                                 ▼
┌──────────────┐              ┌──────────────┐
│  看板 (HTML)  │── REST API ─▶│  FastAPI      │
│  Plotly.js   │              │  main.py      │
│  策略选择/    │              └──────┬───────┘
│  收益曲线/    │                    │
│  分股票明细   │     ┌──────────────┴──────────────┐
└──────────────┘     │                             │
                     ▼                             ▼
              ┌────────────┐              ┌────────────────┐
              │  回测引擎   │              │   数据层        │
              │  backtest  │◀─────────────│                │
              │  portfolio │              │  fetcher.py    │
              │  metrics   │              │  (mootdx)      │
              └─────┬──────┘              │  cache.py      │
                    │                     │  (Parquet)     │
                    ▼                     │  stock_pool.py │
              ┌────────────┐              └────────────────┘
              │  策略插件   │
              │  base.py   │
              │  macd_*.py │
              │  kdj_*.py  │
              │  (你的策略) │
              └────────────┘
```

---

## 项目结构

```
quant-backtester/
├── pyproject.toml              # 项目配置 + uv 依赖
├── README.md
├── docs/DESIGN.md              # 设计文档
├── src/quant_backtester/
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 全局配置
│   ├── data/                   # 数据层
│   │   ├── fetcher.py          #   mootdx 拉取日/周/月K
│   │   ├── cache.py            #   Parquet 缓存 (增量更新)
│   │   └── stock_pool.py       #   股票池 (3309只, 非ST/科创/北交/创业)
│   ├── engine/                 # 回测引擎
│   │   ├── backtest.py         #   主循环 (逐日驱动策略)
│   │   ├── portfolio.py        #   虚拟账户 (现金/持仓/手续费/滑点)
│   │   ├── metrics.py          #   指标计算 (夏普/回撤/胜率/盈亏比)
│   │   └── indicators.py       #   技术指标 (MACD/KDJ/RSI/布林带/ATR)
│   ├── strategies/             # 策略目录 (放这里自动发现)
│   │   ├── base.py             #   策略基类 + Order 交易指令
│   │   ├── registry.py         #   自动扫描发现
│   │   ├── macd_cross.py       #   MACD 金叉死叉
│   │   ├── macd_divergence.py  #   MACD 顶底背离
│   │   ├── kdj_cross.py        #   KDJ 金叉死叉 + 超买
│   │   └── weekly_daily_kdj.py #   周K+日K KDJ 联动
│   └── dashboard/
│       └── templates/index.html # 看板页面
├── tests/                      # 单元测试 (180 个)
├── deploy/                     # 部署文件
│   └── quant-backtester.service # systemd 服务
└── data/cache/                 # K线缓存 (gitignored)
    ├── 600578.parquet           #   每只股票一个文件
    └── stock_pool.json          #   股票池缓存
```

---

## 部署

### Linux 服务器（systemd，开机自启）

```bash
# 1. 先修改 deploy/quant-backtester.service 里的两行路径：
#    WorkingDirectory=  改成你 clone 的目录
#    ExecStart=          改成你 venv 里的 uvicorn 路径
#    (which uvicorn 可查)

# 2. 安装服务
sudo cp deploy/quant-backtester.service /etc/systemd/system/
sudo systemctl daemon-reload

# 3. 启动 + 开机自启
sudo systemctl enable --now quant-backtester

# 4. 验证
curl http://localhost:8100/api/health
# → {"status":"ok","version":"0.2.0"}
```

**管理命令：**

```bash
systemctl status quant-backtester    # 查看状态
systemctl restart quant-backtester   # 重启
journalctl -u quant-backtester -f    # 实时日志
```

**资源限制：** `MemoryMax=800M` `CPUQuota=80%`，防止回测打满 CPU/内存影响其他服务。

### macOS 本地（直接运行）

```bash
cd /root/.hermes/projects/quant-backtester

# 安装依赖
uv pip install -e .

# 启动（三种方式任选）
quant-backtester                                          # CLI 入口
uvicorn quant_backtester.main:app --host 127.0.0.1 --port 8100   # uvicorn
python3 -m uvicorn quant_backtester.main:app --host 127.0.0.1 --port 8100
```

打开浏览器 `http://localhost:8100` 即可看到看板。

> **macOS 不装 systemd**，直接用上述命令启动。关终端即停止，适合本地开发调试。

---

## 看板使用

1. 打开 `http://IP:8100`
2. 下拉列表选择策略（自动发现 `strategies/` 下所有策略）
3. 设置参数：股票数(1-100)、窗口天数(60-500)、每只次数(1-10)、资金
4. 点击 **▶ 开始回测**
5. 等待完成（3只×1次 ≈ 1秒），查看结果：
   - **收益曲线** — 每个任务的权益曲线叠加（Plotly 交互图）
   - **指标卡片** — 平均收益、中位数、最佳/最差、夏普、回撤、胜率、交易次数
   - **分股票明细表** — 每只股票每个窗口的详细指标

---

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 看板页面 |
| `GET` | `/api/health` | 服务状态 |
| `GET` | `/api/strategies` | 可用策略列表 + 描述 |
| `GET` | `/api/stock-pool` | 股票池统计 |
| `GET` | `/api/cache-stats` | K线缓存统计 |
| `POST` | `/api/backtest` | 执行回测 |

### POST /api/backtest

```bash
curl -X POST http://localhost:8100/api/backtest \
  -H "Content-Type: application/json" \
  -d '{"strategy":"MACD金叉死叉","stock_count":5,"window_days":180,"runs_per_stock":3,"initial_capital":100000}'
```

响应：

```json
{
  "strategy": "MACD金叉死叉",
  "elapsed_seconds": 1.5,
  "aggregate": {
    "success_count": 15, "avg_return_pct": 1.9,
    "avg_sharpe": -0.215, "avg_max_drawdown_pct": -21.4,
    "overall_win_rate_pct": 30, "winning_task_pct": 43,
    "total_trades": 89
  },
  "results": [
    {
      "code": "600578", "window_start": "2023-03-15",
      "total_return_pct": 12.3,
      "metrics": {"sharpe_ratio": 1.2, "max_drawdown_pct": -8.5, ...},
      "trades": [{"date":"2023-04-10","action":"buy","price":8.59,...}]
    }
  ]
}
```

---

## 策略开发指南

### 快速开始

在 `src/quant_backtester/strategies/` 下创建一个 `.py` 文件：

```python
# strategies/my_strategy.py
from quant_backtester.strategies.base import BaseStrategy, Order
from quant_backtester.engine.indicators import sma, golden_cross, dead_cross

class MyStrategy(BaseStrategy):
    name = "我的策略"              # 显示在看板下拉列表
    description = "5日线上穿20日线买入，下穿卖出"

    def init(self):
        """回测前调用一次。在此预计算指标。"""
        close = self.daily["close"]
        self.ma5 = sma(close, 5)
        self.ma20 = sma(close, 20)

    def next(self, i: int) -> list[Order]:
        """每天调用一次。i=当前索引。返回交易指令列表。"""
        if i < 20:
            return []

        if self.ma5.iloc[i] > self.ma20.iloc[i] and self.ma5.iloc[i-1] <= self.ma20.iloc[i-1]:
            return [Order.buy(pct=1.0, reason="5日线上穿20日线")]

        if self.ma5.iloc[i] < self.ma20.iloc[i] and self.ma5.iloc[i-1] >= self.ma20.iloc[i-1]:
            return [Order.sell(pct=1.0, reason="5日线下穿20日线")]

        return []
```

**刷新看板页面** → 下拉列表自动出现"我的策略" → 选中即可回测。

### 策略能用的数据

| 属性 | 类型 | 说明 |
|------|------|------|
| `self.daily` | DataFrame | 日线 OHLCV，索引=日期，列: open/close/high/low/volume |
| `self.weekly` | DataFrame | 周线 OHLCV，索引已对齐到日线 |
| `self.monthly` | DataFrame | 月线 OHLCV，索引已对齐到日线 |
| `self.has_position` | bool | 当前是否持仓 |
| `self.profit_pct` | float | 当前持仓盈亏 (%) |
| `self.cost` | float | 持仓成本价 |
| `self.cash` | float | 现金余额 |

### 引擎保证

- **防未来函数** — `next(i)` 里只能访问 `daily.iloc[i]` 及之前的数据
- **sell 无持仓 → 跳过** — 引擎自动拦截，记录警告日志
- **buy 已有持仓 → 跳过** — 单股模式不重复买入
- **Order 支持 pct** — 买入时 `pct` = 仓位比例，卖出时 `pct` = 卖出比例

### 内置指标工具

在 `init()` 里调用，存为成员变量：

| 函数 | 说明 |
|------|------|
| `sma(series, n)` | N日简单均线 |
| `ema(series, n)` | N日指数均线 |
| `sma_multi(series, [5,10,20,60])` | 一次算多条 SMA → DataFrame |
| `ema_multi(series, [12,26])` | 一次算多条 EMA → DataFrame |
| `add_mas(df)` | 为 OHLCV DataFrame 添加 ma5/10/20/60 列 |
| `macd(close, fast, slow, signal)` | MACD → (DIF, DEA, 柱) |
| `kdj(high, low, close, n, k_p, d_p)` | KDJ → (K, D, J) |
| `rsi(close, n)` | RSI |
| `bollinger(close, n, k)` | 布林带 → (上轨, 中轨, 下轨) |
| `atr(high, low, close, n)` | 平均真实波幅 |
| `golden_cross(fast, slow)` | 金叉点 (布尔 Series) |
| `dead_cross(fast, slow)` | 死叉点 (布尔 Series) |
| `find_peaks(series, order)` | 局部高点 |
| `find_troughs(series, order)` | 局部低点 |

### 跨周期策略示例

```python
class WeeklyFilterDaily(BaseStrategy):
    name = "周线过滤日线"
    description = "周K > 20周线的股票，日K金叉买入"

    def init(self):
        self.w_ma20 = sma(self.weekly["close"], 20)
        d_dif, d_dea, _ = macd(self.daily["close"])
        self.d_golden = golden_cross(d_dif, d_dea)

    def next(self, i):
        if i < 20:
            return []
        # 周线上涨趋势 + 日线金叉
        if self.weekly["close"].iloc[i] > self.w_ma20.iloc[i] and self.d_golden.iloc[i]:
            return [Order.buy(pct=1.0, reason="周线上涨+日线MACD金叉")]
        return []
```

---

## 配置

所有可调参数在 `src/quant_backtester/config.py`：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `FASTAPI_HOST` | `"0.0.0.0"` | 监听地址 |
| `FASTAPI_PORT` | `8100` | 监听端口 |
| `DAILY_BEGIN` | `"2015-01-01"` | 日线最早拉取日期 |
| `EXCLUDE_PREFIXES` | `("688","8","900","301")` | 排除板块 |
| `EXCLUDE_300` | `True` | 排除创业板 |

---

## 数据存储

```
data/cache/
├── {code}.parquet      # 每只股票日线 OHLCV (62KB/只)
└── stock_pool.json     # 过滤后股票池 (3309只)
```

| 数据 | 单只大小 | 4000只合计 |
|------|----------|-----------|
| 日线 (10年) | 62 KB | 241 MB |
| 周线 (resample) | — | — |
| 月线 (resample) | — | — |
| **总计** | **~100 KB** | **~395 MB** |

缓存策略：首次拉到→存 Parquet → 再次拉到→只拉增量日期（最后缓存日+1 ~ 今天）。

---

## 测试

```bash
# P4 阶段填充单元测试
pytest tests/ -v
```

---

## 回测引擎详解

### 一次回测 = 1股 × 180天窗口 × 1策略

1. 从缓存/通达信获取股票全量日线
2. 随机选一个 180 天窗口
3. Resample 生成周线/月线，对齐索引到日线
4. `strategy.init()` 预计算指标
5. 逐日 `strategy.next(i)` → 返回 `list[Order]`
6. 引擎校验并执行：buy/sell + 手续费(万三) + 滑点(0.1%)
7. 记录每日权益曲线
8. 回测结束强制平仓
9. 计算夏普/最大回撤/胜率/盈亏比等指标

### 指标说明

| 指标 | 含义 |
|------|------|
| **夏普比率** | 每冒1%风险，赚了多少超额收益。>1及格，>2优秀 |
| **最大回撤** | 历史上从最高点到最低点的最大亏损幅度 |
| **胜率** | 盈利交易次数 / 总卖出次数 |
| **盈亏比** | 平均盈利 / 平均亏损 |
| **Calmar比率** | 年化收益 / 最大回撤 |

---

## 技术栈

| 层次 | 选型 |
|------|------|
| Web 框架 | FastAPI |
| 包管理 | uv |
| 数据源 | mootdx (通达信免费接口) |
| 数据缓存 | Parquet (pyarrow, Snappy 压缩) |
| 数据分析 | pandas + numpy + scipy |
| 可视化 | Plotly.js (CDN) |
| Python | >= 3.11 |
