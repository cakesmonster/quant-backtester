# 日晷 Sundial — A股市场数据看板 + 量化回测引擎

**一体化 A 股看板**：每日复盘、热榜追踪、个股分析、策略回测、模拟账户，全部端口 8100。

```bash
systemctl start sundial    # 启动 → http://localhost:8100
```

---

## 架构

```
                    浏览器 (http://IP:8100)
                           │
                    ┌──────▼──────┐
                    │   FastAPI   │  sundial.main:app
                    │   :8100     │
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │  sundial     │ │ 回测引擎     │ │ 策略注册表   │
    │  services/   │ │ engine/     │ │ strategies/ │
    │  看板聚合     │ │ 逐日驱动     │ │ 6个内置策略  │
    │  队友互相关   │ │ 指标计算     │ │ 热加载       │
    └──────┬──────┘ └──────┬──────┘ └─────────────┘
           │               │
    ┌──────▼───────────────▼──────┐
    │         数据层               │
    │  mootdx   Baostock  AkShare │
    │  同花顺热榜  东方财富 push2ex │
    │  Parquet 缓存     │
    └─────────────────────────────┘
```

回测引擎以**库**形式集成在 sundial 进程内（`src/quant_backtester/`），不再独立启动服务。所有功能通过 `/api/backtest/*` 端点访问。

---

## 项目结构

```
sundial/
├── pyproject.toml              # 项目配置 + 依赖
├── .env                        # 环境变量（API 密钥等）
├── deploy/sundial.service      # systemd 服务
├── src/
│   ├── sundial/                # 日晷主应用
│   │   ├── main.py             # FastAPI 入口（端口 8100）
│   │   ├── config.py           # HOST/PORT 配置
│   │   ├── db.py               # SQLite 管理
│   │   ├── services/           # 看板聚合服务
│   │   │   ├── dashboard.py    # t/api/dashboard（队友/热榜/复盘…）
│   │   │   ├── sentiment.py   # 情绪仪表盘
│   │   │   ├── ladder.py      # 连板天梯
│   │   │   └── hot_rank.py    # 热榜查询
│   │   ├── data/               # 数据源适配层
│   │   │   ├── ths_api.py     # 同花顺热榜（含涨跌幅 rise_and_fall）
│   │   │   ├── ths_trade_api.py # 同花顺模拟交易
│   │   │   ├── eastmoney_api.py # 东方财富 push2ex
│   │   │   └── baostock_api.py  # Baostock 指数
│   │   └── dashboard/          # SPA 前端
│   └── quant_backtester/       # 回测引擎（库）
│       ├── engine/             # 回测核心
│       ├── strategies/         # 策略插件（热加载）
│       └── data/               # K线缓存
├── tests/                      # 单元测试
├── scripts/                    # 工具脚本
└── data/cache/                 # K线缓存（gitignored）
```

---

## 页面

| 页面 | 路由 | 功能 |
|------|------|------|
| 每日复盘 | `/review` | 涨停/跌停/炸板情绪 + 连板天梯 |
| 热榜 | `/hotrank` | 同花顺一小时热股榜（11:30 / 15:00 / 21:00） |
| 个股分析 | `/stock` | 日K + 分时图 + 找队友（分时图互相关） |
| 策略回测 | `/backtest` | 6个内置策略 + 自定义策略热加载 |
|| 模拟账户 | `/account` | 同花顺模拟盘资产/持仓/收益趋势/成交记录/资金流 |

---

## 数据源

| 数据 | 来源 | 说明 |
|------|------|------|
| 涨停/跌停/炸板 | 东方财富 push2ex | 支持历史 date 查询 |
| 指数（沪/深/创） | Baostock | 含成交额 |
| 科创50 | AkShare | 补 Baostock 缺口 |
| 热榜排名 + 概念 + 涨跌幅 | 同花顺 THS API `dq.10jqka.com.cn` | `rise_and_fall` 字段直接含涨跌幅，APScheduler 每小时采集 |
| 个股日K | 通达信 mootdx | Parquet 缓存，与回测同源 |
| 分时图 | 通达信 mootdx 1分钟K线 | `frequency=7, offset=240` |
| 找队友 | 通达信 mootdx 1分钟K线 | 滑动窗口 Pearson r 互相关 |
| 模拟交易 | 同花顺模拟炒股 API | 服务端撮合 |

---

## 找队友（teammates）

根据**概念板块**筛选同板块股票，拉取 1 分钟 K 线后**滑动窗口 Pearson r 互相关**分组：

1. 收集热榜 + 连板天梯所有股票的 THS 概念标签
2. 按概念分组，同组内两两拉取通达信 1 分钟 K 线（`frequency=7, offset=240`）
3. 计算分钟涨跌幅序列，15 分钟窗口滑动 Pearson r（步长 3，阈值 0.6）
4. 连通分量分组，共享概念即合并
5. 输出队友列表 + 共享概念 + 真实 r 值

算法源自 board_monitor `signals/team.py` `compute_teammates()`。

---

## API

### 看板

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/dashboard` | 聚合端点，一次返回全部数据 |
| `GET` | `/api/review` | 每日复盘（情绪+天梯） |
| `GET` | `/api/hotrank?date=&slot=` | 热榜历史查询 |
| `GET` | `/api/stock/{code}` | 日K + 分时图 |
| `GET` | `/api/account` | 模拟账户 |
| `GET` | `/health` | 服务状态 |

### 回测

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/backtest/strategies` | 策略列表 |
| `POST` | `/api/backtest/run` | 执行回测 |

```bash
curl -X POST http://localhost:8100/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{"strategy":"MACD金叉死叉","stock_count":5,"window_days":180,"runs_per_stock":2}'
```

---

## 部署

### systemd（生产）

```bash
sudo cp deploy/sundial.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sundial
```

服务文件 `deploy/sundial.service`：

```ini
[Service]
WorkingDirectory=/root/.hermes/projects/sundial
ExecStart=/usr/local/lib/hermes-agent/venv/bin/python3 -m uvicorn sundial.main:app --host 127.0.0.1 --port 8100
MemoryMax=600M
CPUQuota=60%
```

### 管理命令

```bash
systemctl status sundial
systemctl restart sundial
journalctl -u sundial -f
```

### 本地开发

```bash
uv pip install -e .
python3 -m uvicorn sundial.main:app --host 127.0.0.1 --port 8100
```

---

## 配置

### pyproject.toml

```toml
[project]
name = "sundial"
version = "0.1.0"
description = "日晷 — A股市场数据看板"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]",
    "baostock",
    "akshare",
    "httpx",
    "pandas",
    "mootdx",
    "numpy",
    "scipy",
    "apscheduler",
]
```

### 环境变量（可选 .env）

项目根目录创建 `.env`（不提交 git）：

```bash
# 同花顺模拟炒股（用于 /api/account 同步）
THS_USRID=116365878
THS_DEPARTMENT=997376

# 同花顺交易 API
THS_TRADE_API=http://trade.10jqka.com.cn:8088
```

### sundial/config.py

```python
HOST = os.environ.get("SUNDIAL_HOST", "127.0.0.1")
PORT = int(os.environ.get("SUNDIAL_PORT", "8100"))
```

---

## 回测引擎

### 内置策略（6 个）

| 策略 | 买入 | 卖出 |
|------|------|------|
| KDJ 金叉死叉 | 日线 KDJ 金叉 | 死叉 / J>100 / K>80 |
| MACD 金叉死叉 | 日线 MACD 金叉 | 死叉 |
| MACD 顶底背离 | 日线 MACD 底背离 | 顶背离 |
| 周线+日线 KDJ 联动 | 周K 金叉区间内日K 金叉 | 日K 死叉/J>100/K>80 / 周K 死叉强制清仓 |
| 均线趋势 | 日线 MA5 上穿 MA10 + 周线多头确认 | RSI>80 或跌破 MA5 |
| MA 多头趋势 | MA5>10>20>60 趋势向上 + MA5 上穿 MA10 | 跌破 MA5 |

### 策略开发

在 `src/quant_backtester/strategies/` 新建 `.py` 文件，继承 `BaseStrategy`：

```python
from quant_backtester.strategies.base import BaseStrategy, Order
from quant_backtester.engine.indicators import add_mas, rsi

class MyStrategy(BaseStrategy):
    name = "我的策略"
    description = "日线MA5上穿MA10买入，跌破MA5卖出"

    def init(self):
        add_mas(self.daily)  # ma5/10/20/60
        self.daily["rsi"] = rsi(self.daily["close"], n=14)

    def next(self, i: int) -> list[Order]:
        if i < 60: return []
        if self.daily["ma5"].iloc[i] > self.daily["ma10"].iloc[i] and \
           self.daily["ma5"].iloc[i-1] <= self.daily["ma10"].iloc[i-1]:
            return [Order.buy(pct=1.0, reason="金叉")]
        if self.daily["rsi"].iloc[i] > 80:
            return [Order.sell(pct=1.0, reason="RSI超买")]
        return []
```

写完 → 点前端「🔄 刷新策略」或 `POST /api/backtest/strategies` → 无需重启。

### 可用数据

| 属性 | 说明 |
|------|------|
| `self.daily` | 日线 OHLCV，索引=日期 |
| `self.weekly` | 周线，索引对齐日线 |
| `self.monthly` | 月线，索引对齐日线 |
| `self.has_position / profit_pct / cost / cash` | 持仓状态 |

### 引擎保证

- 防未来函数（`next(i)` 只能访问 `iloc[i]` 及之前）
- sell 无持仓 → 跳过
- buy 已有持仓 → 跳过（单股模式）
- 手续费万三 + 滑点 0.1%
- 每手 100 股取整
- T+1（买入日锁定，次日解锁）
- 涨跌停 ±10%

### 内置指标工具

在 `init()` 里调用：`sma / ema / macd / kdj / rsi / bollinger / atr / golden_cross / dead_cross / find_peaks / find_troughs`

---

## A股规则（引擎强制）

| 规则 | 实现 |
|------|------|
| T+1 | `bought_day_idx` 记录买入日，次日解锁 |
| 涨跌停 ±10% | 涨停跳过 buy，跌停跳过 sell |
| 一手 100 股 | 买入量向下取整到 100 倍数 |

---

## 数据存储

### K线缓存

`data/cache/{code}.parquet` — 每只股票日线，从通达信首次拉取后缓存，后续增量更新。

### SQLite

`src/data/sundial.db`：
- `hot_rank_snapshot` — 热榜快照（每小时采集，盘中实时）
- `account_snapshot` — 模拟账户快照（盘中每10分钟 + 盘后15:05同步）
- `trade_record` — 成交记录（monitor 买入/卖出自动写入）

---

## 测试

```bash
pytest tests/ -q
# sundial: DB / 情绪 / 天梯 / API / 配置
# quant_backtester: indicators / portfolio / engine / strategies / metrics / cache / stock_pool / fetcher / registry
```

---

## 技术栈

| 层 | 选型 |
|----|------|
| Web 框架 | FastAPI |
| 数据源 | mootdx / Baostock / AkShare / 同花顺 / 东方财富 |
| 数据缓存 | Parquet (pyarrow) + SQLite |
| 数据分析 | pandas + numpy + scipy |
| 定时任务 | APScheduler（进程内，不依赖 hermes cron） |
| 可视化 | Plotly.js (CDN) |
| 部署 | systemd + uvicorn |
| Python | >= 3.11 |
