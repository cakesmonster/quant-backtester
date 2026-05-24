# 量化回测框架 — 设计文档 v0.2

> **所有决策已定稿** | 下一步：搭项目骨架

---

## 0. 已决策汇总

| # | 决策 | 结论 |
|---|------|------|
| 1 | 策略架构 | 通用基类 + 策略放 `strategies/` 目录，自动发现。引擎负责数据对齐（周K/月K索引对齐到日线），策略直接用 `self.weekly.iloc[i]` 访问跨周期数据 |
| 2 | 仓位管理 | **B** — `Order` 支持 `pct` 参数（买入 30% 仓位、卖出 20% 持仓等）。多股组合留扩展点 `Strategies/multi/` |
| 3 | 股票池 | **C** — 全部 A 股排除 ST、688(科创)、8/9(北交/B股)、300(创业) |
| 4 | 看板 | **B** — FastAPI 托管交互式 HTML 页面，`IP:PORT` 直接访问，策略下拉选择器自动刷新 |

---

## 1. 项目定位

一个**本地回测沙盒**，用通达信历史K线跑自定义交易策略，输出收益曲线 + 多维度指标。

**是：** 回测引擎 + 策略插件框架 + 交互式看板
**不是：** 实盘交易系统、参数优化器（网格搜索）

---

## 2. 架构

```
浏览器 IP:8100
    │
    ▼
┌──────────────────────────────────────────────┐
│                FastAPI (:8100)                │
│                                              │
│  GET  /                交互式看板 (HTML)      │
│  GET  /api/strategies  策略列表              │
│  POST /api/backtest    启动回测              │
│  GET  /api/result/{id} 回测结果              │
│  GET  /api/stock-pool  股票池状态            │
└──────────────┬───────────────────────────────┘
               │
    ┌──────────┴──────────┐
    │                     │
    ▼                     ▼
┌──────────────┐   ┌──────────────────┐
│ 数据层        │   │  回测引擎         │
│              │   │                  │
│ fetcher.py   │   │ portfolio.py     │
│ (mootdx拉取) ├──►│ (虚拟账户)        │
│              │   │                  │
│ cache.py     │   │ backtest.py      │
│ (Parquet缓存)│   │ (主循环)          │
└──────────────┘   │                  │
                   │ metrics.py       │
                   │ (夏普/回撤/胜率)  │
                   └────────┬─────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │  策略目录         │
                   │  strategies/     │
                   │  ├── base.py     │
                   │  ├── macd.py     │
                   │  ├── kdj.py      │
                   │  └── ...         │
                   │  (自动发现)       │
                   └──────────────────┘
```

### 目录结构

```
quant-backtester/
├── pyproject.toml
├── README.md
├── docs/DESIGN.md
├── src/
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 全局配置（端口/缓存路径/默认参数）
│   ├── data/
│   │   ├── fetcher.py          # mootdx 数据拉取
│   │   ├── cache.py            # Parquet 缓存 (data/cache/{code}.parquet)
│   │   └── stock_pool.py       # 股票池管理（排除规则 + 随机采样）
│   ├── engine/
│   │   ├── backtest.py         # 回测主循环
│   │   ├── portfolio.py        # 模拟账户
│   │   ├── metrics.py          # 指标计算（夏普/回撤/胜率等）
│   │   └── indicators.py       # 技术指标工具（MACD/KDJ/RSI/均线）
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base.py             # 策略抽象基类
│   │   ├── registry.py         # 自动发现 + 注册
│   │   └── (策略文件放这里)     # macd_cross.py, kdj_oversold.py ...
│   └── dashboard/
│       ├── templates/
│       │   └── index.html       # 看板页面（含 Plotly JS CDN）
│       └── static/              # 预留
├── tests/
└── data/cache/                  # K线缓存 (gitignore)
```

---

## 3. 策略插件设计（核心）

### 3.1 开发流程

你告诉我一个策略思路 → 我在 `strategies/` 下创建一个 `.py` 文件 → 你刷新看板页面就能看到它出现在下拉列表里。

**自动发现：** FastAPI 启动时扫描 `strategies/` 目录，找到所有继承 `BaseStrategy` 的类，注册到策略列表。不需要手动改任何配置文件。

### 3.2 策略基类

```python
class BaseStrategy(ABC):
    # ── 元信息（必须定义）──
    name: str                   # 策略名称，显示在看板下拉列表
    description: str            # 一句话描述

    # ── 数据（引擎注入，策略直接用）──
    daily: pd.DataFrame         # 日线 OHLCV，索引 = 日期，列: open/high/low/close/volume
    weekly: pd.DataFrame        # 周线 OHLCV，索引已对齐到日线（同一行=同一天所属那周）
    monthly: pd.DataFrame       # 月线 OHLCV，同上

    # ── 账户状态（引擎实时更新）──
    has_position: bool          # 当前是否持仓
    position_pct: float         # 当前仓位占比 (0.0 ~ 1.0)
    profit_pct: float           # 当前持仓盈亏 (%)
    cost: float                 # 当前持仓成本价
    cash: float                 # 当前现金

    # ── 策略必须实现的方法 ──

    @abstractmethod
    def init(self):
        """回测开始前调用一次。在这里预计算指标。"""
        ...

    @abstractmethod
    def next(self, i: int) -> list[Order]:
        """
        每个交易日调用一次。

        Args:
            i: 当前日期在 daily 中的索引 (0 = 第一天)

        Returns:
            Order 列表。可以为空（不做操作）。
            支持多个 Order（如先卖30%再止盈卖20%）。

        防未来函数保证：
            - self.daily.iloc[i] 是"刚收盘这天"，你可以用
            - self.daily.iloc[i+1] 会报错（引擎层面阻止）
            - 所有 self.xxx(i) 方法只返回 <= i 的数据
        """
        ...


class Order:
    """交易指令"""
    action: Literal["buy", "sell"]
    pct: float          # 0.0 ~ 1.0（买入=%仓位，卖出=%持仓）
    reason: str = ""    # 记录原因，用于交易明细
```

### 3.3 内置指标工具

引擎提供指标计算辅助方法，策略在 `init()` 里调用，存为成员变量，`next()` 里直接用：

```python
class BaseStrategy:
    # 均线
    def sma(self, col: str, n: int) -> pd.Series
    def ema(self, col: str, n: int) -> pd.Series

    # MACD: 返回 (dif, dea, histogram)
    def macd(self, fast=12, slow=26, signal=9) -> tuple

    # KDJ: 返回 (k, d, j)
    def kdj(self, n=9, k_period=3, d_period=3) -> tuple

    # RSI
    def rsi(self, n=14) -> pd.Series

    # 布林带: 返回 (upper, middle, lower)
    def bollinger(self, n=20, k=2) -> tuple

    # 成交量均线
    def vol_ma(self, n=20) -> pd.Series

    # ATR（平均真实波幅）
    def atr(self, n=14) -> pd.Series
```

### 3.5 首批策略

**策略引擎保证：** `sell` 时无持仓 → 引擎自动跳过（不报错但记警告日志），策略无需自行判断 `has_position`。

#### 策略1：日线 MACD 背离

```
macd_divergence.py — MACD 顶/底背离交易

买入（底背离）：股价创新低，MACD DIF 未创新低（看涨背离）
卖出（顶背离）：股价创新高，MACD DIF 未创新高（看跌背离）

实现要点：
- 跟踪最近 N 天的价格高/低点 和 MACD DIF 高/低点
- 用 scipy.signal.argrelextrema 找局部极值点
- 背离确认：价格方向与 DIF 方向相反
```

#### 策略2：日线 KDJ 金叉死叉

```
kdj_cross.py — KDJ 金叉买 / 死叉+超买卖

买入：K 上穿 D（金叉），且前一根 K <= D
卖出（任一条件）：
  - K 下穿 D（死叉）
  - J > 100（超买）
  - K > 80（超买）

参数：N=9, K_period=3, D_period=3（标准 KDJ 参数）
```

#### 策略3：周线 KDJ + 日线 KDJ 联动

```
weekly_daily_kdj.py — 周线趋势内日线操作

前提：周K KDJ 处于金叉状态（周线 K > D）→ "可操作区间"
买入：在可操作区间内，日K KDJ 金叉 → 买入
卖出（任一条件）：
  - 日K KDJ 死叉
  - 日K J > 100
  - 日K K > 80

注意：如果周K KDJ 进入死叉（K < D），即使日K金叉也不买。
      周K死叉时，如果持仓中，执行卖出。
```

### 3.6 跨周期示例

周K/月K的索引已由引擎自动对齐到日线：

```python
class WeeklyMACDCross(BaseStrategy):
    name = "周线MACD金叉+日线放量"
    description = "周K MACD金叉日，日K成交量>20日均量2倍，买入"

    def init(self):
        # 在周线上算 MACD
        w_dif, w_dea, _ = self.macd_on('weekly', 12, 26, 9)
        self.w_golden_cross = (w_dif > w_dea) & (w_dif.shift(1) <= w_dea.shift(1))
        # 日线成交量均线
        self.vol_ma20 = self.sma('volume', 20)

    def next(self, i):
        if (self.w_golden_cross.iloc[i] and                          # 这周金叉
            self.daily.iloc[i]['volume'] > self.vol_ma20.iloc[i] * 2):  # 放量2倍
            return [Order.buy(pct=1.0, reason="周线MACD金叉+放量")]
        return []
```

---

## 4. 数据层

### 4.1 数据源

- **mootdx**（通达信免费接口）
- 日线: `c.k(code, begin='...', end='...')` — 无上限，按日期区间
- 周线: `c.bars(code, frequency='week', start=0, offset=800)` — 800根约16年
- 月线: `c.bars(code, frequency='mon', start=0, offset=800)` — 全量

### 4.2 缓存策略（增量更新）

**Parquet 按股票分文件：** `data/cache/{code}.parquet`

```
首次随机到 600578 (日期 2026-04-20):
  c.k(code, begin='2015-01-01', end='2026-04-20')  → 保存 600578.parquet

再次随机到 600578 (日期 2026-05-20):
  读取 600578.parquet → 最后一条日期 = 2026-04-20
  c.k(code, begin='2026-04-21', end='2026-05-20')  → append 到 600578.parquet
```

**存储实测：**

| 周期 | 单只股票 | 4000 只 |
|------|----------|---------|
| 日线 (2678行, 10年) | 62 KB | 241 MB |
| 周线 (800根, 16年) | 26 KB | 100 MB |
| 月线 (285根, 24年) | 14 KB | 54 MB |
| **合计** | **~100 KB** | **~395 MB** |

**结论：全部 A 股日/周/月线全量缓存不到 400MB，完全不需要担心存储。** 拉一次存下来，以后回测秒读。周线/月线从日线 resample 生成（不单独缓存），进一步节省空间。

### 4.3 股票池

**全部A股排除规则：**

| 排除条件 | 前缀/关键字 | 原因 |
|----------|------------|------|
| ST 股 | `ST`, `*ST` | 风险警示 |
| 科创板 | `688` | 20%涨跌幅，不同规则 |
| 北交所 | `8` | 30%涨跌幅 |
| B 股 | `900` | 外币交易 |
| 创业板 | `300` | 鹤老大战法不碰 |

**股票池初始化：** 首次运行时，调用 mootdx `stock_count` 获取全市场股票列表 → 过滤 → 缓存名单到 `data/cache/stock_pool.json`。

---

## 5. 回测引擎

### 5.1 输入参数（看板页面可填）

```json
{
  "strategy": "macd_cross",
  "stock_count": 10,
  "window_days": 180,
  "runs_per_stock": 3,
  "initial_capital": 100000,
  "commission": 0.0003,
  "date_range": {"start": "2021-01-01", "end": "2026-01-01"}
}
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `strategy` | — | 策略名称（从下拉列表选） |
| `stock_count` | 10 | 随机选几只股票 |
| `window_days` | 180 | 回测窗口（交易日） |
| `runs_per_stock` | 3 | 每只股票随机几个窗口 |
| `initial_capital` | 100000 | 初始资金 |
| `commission` | 0.0003 | 手续费（万三） |
| `date_range` | 最近5年 | 时间范围 |

### 5.2 回测流程

```
每次回测任务 = 1只股票 × 1个180天窗口 × 1个策略

1. 从缓存拉取股票全部日线（增量更新）
2. 在 date_range 内随机选一个起点，取 window_days 天
3. Resample 生成周线/月线，对齐索引到日线
4. 初始化策略 → 调用 strategy.init()
5. 逐日遍历 i = 0..179:
   a. 调用 orders = strategy.next(i)
   b. 遍历每个 Order 并校验：
      - sell 且 !has_position → 引擎跳过此 Order，记录警告
      - buy 且 has_position → 引擎跳过（单股模式不重复买入，后续多股模式放开）
      - buy 时按 pct 计算买入股数（100股取整），扣手续费+滑点
      - sell 时按 pct 计算卖出股数，加回现金，扣手续费+滑点
   c. 记录当日权益
6. 计算指标：收益率/夏普/回撤/胜率/交易明细
```

**⚠️ 引擎层面的买卖校验（防止策略 bug）：**

```python
for order in strategy.next(i):
    if order.action == "sell" and not self.has_position:
        log.warning(f"策略试图卖出但无持仓，跳过: {order.reason}")
        continue
    if order.action == "buy" and self.has_position:
        log.warning(f"策略试图买入但已有持仓（单股模式），跳过: {order.reason}")
        continue
    execute(order)
```

### 5.3 防未来函数保证

引擎层面保证：在 `next(i)` 执行期间，如果策略尝试访问 `self.daily.iloc[i+1]` 或之后的任何数据，引擎会**抛出异常**。这是通过在 `next()` 调用前后设置/清除一个"可见范围"标记来实现的。

---

## 6. 输出

### 6.1 看板页面

一个 FastAPI 托管的 HTML 页面（`GET /`），包含：

```
┌─────────────────────────────────────────────────────┐
│  🔬 量化回测看板                                     │
│                                                     │
│  策略: [MACD金叉放量 ▼]  股票数:[10]  窗口:[180]天   │
│  重复:[3]次/股  资金:[100000]  时间:[2021→2026 ▼]    │
│  [▶ 开始回测]                                       │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │          📈 收益曲线 (Plotly 交互图)          │    │
│  │         每个任务的权益曲线叠加                 │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌──────────┬──────────┬──────────┬──────────┐      │
│  │ 总收益率  │ 年化收益  │ 夏普比率  │ 最大回撤  │      │
│  │  +12.3%  │  +8.5%   │   1.32   │  -15.2%  │      │
│  ├──────────┼──────────┼──────────┼──────────┤      │
│  │ 胜率      │ 盈亏比    │ 交易次数  │ 任务数    │      │
│  │  55%     │  1.8     │   234    │   30     │      │
│  └──────────┴──────────┴──────────┴──────────┘      │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │         📋 分股票明细 (可排序表格)             │    │
│  │  股票   │ 窗口           │ 收益  │ 夏普 │回撤│    │
│  │  600578 │ 2023-03~2023-09│+12%  │ 1.2 │-8% │    │
│  │  600578 │ 2024-06~2024-12│ -3%  │-0.3 │-15%│    │
│  │  ...    │ ...           │ ...   │ ...  │... │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │         📝 交易记录 (可展开)                   │    │
│  │  日期     │代码  │方向│价格  │数量 │盈亏 │原因  │    │
│  │  2023-04 │600578│买  │8.59 │1100 │  —  │金叉  │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

**技术实现：** 纯 HTML + Plotly.js CDN + Vanilla JS。FastAPI 返回静态 HTML，JS 通过 `/api/*` 端点拉数据渲染。浏览器访问 `http://服务器IP:8100` 即可查看。

**策略切换：** 切换下拉列表自动刷新可用策略列表（`GET /api/strategies`），无需重启服务。新策略文件放到 `strategies/` 目录后刷新页面即可看到。

### 6.2 API 端点

```
GET  /                     → 看板 HTML 页面
GET  /api/strategies       → ["macd_cross", "kdj_oversold", ...]
POST /api/backtest         → { task_id: "uuid" }
GET  /api/backtest/{id}    → { status, progress, result }
GET  /api/stock-pool       → { total: 3850, last_updated: "..." }
```

---

## 7. 技术栈

| 层次 | 选型 | 理由 |
|------|------|------|
| Web 框架 | FastAPI | WebSocket 原生支持，后台任务 |
| 数据拉取 | mootdx | 免费通达信接口，无官方限流 |
| 数据缓存 | Parquet (pyarrow) | 列式存储，读取极快 |
| 数据分析 | pandas + numpy | 指标计算标配 |
| 图表 | Plotly.js (CDN) | 交互式，无需安装，浏览器直接渲染 |
| 前端 | Vanilla HTML + JS | 零依赖，一个文件搞定 |
| 异步 | asyncio | FastAPI 原生 |

---

## 8. 开发计划

| 阶段 | 内容 | 产出 |
|------|------|------|
| **P0** | 数据层打通 | `fetcher.py` + `cache.py` + `stock_pool.py`，能拉到任意股票5年日线并缓存 |
| **P1** | 策略接口 + 引擎 | `base.py` + `backtest.py` + `portfolio.py`，跑通一个简单策略（MACD金叉） |
| **P2** | 指标计算 | `indicators.py` + `metrics.py`，输出夏普/回撤/胜率 |
| **P3** | 看板页面 | `index.html` + FastAPI 路由，交互式回测 |
| **P4** | 首批 3 个策略 | `macd_divergence.py` + `kdj_cross.py` + `weekly_daily_kdj.py` |

---

*文档版本: v0.3 | 已定稿，准备开工 P0*
