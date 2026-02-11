# AI Trading System

AI-Augmented Swing Trading System for BTC/ETH（3–7天持仓周期、低倍杠杆）

## 项目概述

本系统结合**传统技术指标**与**通用大模型（LLM）现场分析**，核心目标是**降低回撤、过滤低质量交易、提升风险调整后收益**。

### 核心设计原则

- 指标负责"发现机会"，AI 负责"否决与调节"
- AI 不直接下单，只输出结构化建议
- 任何交易都必须通过硬风控规则
- 系统支持 AI 不可用时的安全降级

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repo-url>
cd AI-Trading

# 创建虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 安装依赖
pip install -e .
# 或开发模式
pip install -e ".[dev]"
```

### 2. 配置

```bash
# 复制示例配置
cp config.example.env .env

# 编辑 .env 填入你的 API 密钥
```

### 3. 运行

```bash
# 单次运行（拉数据 → 决策 → 执行/记录）
python -m ai_trading.main once

# 循环运行（每15分钟一轮）
python -m ai_trading.main loop --interval-min 15

# 查看帮助
python -m ai_trading.main --help
```

### 4. 回测（BTC-only，三组对比）

系统内置三组实验：
- `baseline`：纯规则（不使用 AI）
- `ai_filter`：AI 仅做放行/拒绝
- `ai_filter_sizing`：AI 放行+按置信度调节仓位

#### 方式 A：使用本地 CSV（推荐，可复现实验）

```bash
python -m ai_trading.main backtest \
  --ohlcv-4h-csv data/btc_4h.csv \
  --ohlcv-1d-csv data/btc_1d.csv \
  --output-dir data/backtest/run_2026_02_12 \
  --segment trend_window,2023-01-01,2023-06-30 \
  --segment range_window,2023-07-01,2023-12-31
```

#### 方式 B：直接拉 Binance 历史数据（会使用缓存）

```bash
python -m ai_trading.main backtest \
  --output-dir data/backtest/latest \
  --limit-4h 1500 \
  --limit-1d 1000 \
  --ai-provider heuristic
```

#### 回测输出说明

运行后会在 `output-dir` 下生成：
- `summary.json`：总览指标 + Go/No-Go 判定
- `go_no_go.md`：可直接阅读的决策结论
- `baseline/`、`ai_filter/`、`ai_filter_sizing/`：
  - `trades.csv`：成交明细
  - `equity_curve.csv`：权益曲线
  - `metrics.json`：全局指标（最大回撤、恢复时间、期望值、交易频率等）
  - `segment_metrics.json`：分段指标（如趋势段/震荡段）

## 项目结构

```
AI-Trading/
├── pyproject.toml          # 项目配置与依赖
├── config.example.env      # 配置示例
├── README.md               # 本文件
├── Framework.md            # 系统设计文档
├── data/                   # 数据存储目录
│   └── journal/            # 交易日志 (JSONL)
└── src/ai_trading/         # 源代码
    ├── main.py             # CLI 入口
    ├── config.py           # 配置加载
    ├── data/               # 数据采集
    │   └── binance.py      # Binance 数据接口
    ├── features/           # 特征计算
    │   └── indicators.py   # 技术指标
    ├── strategy/           # 策略模块
    │   └── candidates.py   # 候选交易生成
    ├── ai/                 # AI 模块
    │   ├── openrouter_client.py  # OpenRouter 客户端
    │   └── schemas.py      # 输入输出 Schema
    ├── risk/               # 风控模块
    │   └── rules.py        # 硬风控规则
    ├── backtest/           # 回测模块
    │   ├── runner.py       # 回测引擎与结果产出
    │   ├── metrics.py      # 评估指标与 Go/No-Go 规则
    │   └── data.py         # 历史数据加载与缓存
    ├── exec/               # 执行模块
    │   ├── paper.py        # 纸交易
    │   └── binance_live.py # 实盘执行
    ├── journal/            # 日志模块
    │   └── store.py        # 交易记录存储
    └── utils/              # 工具模块
        └── logging.py      # 结构化日志
```

## 当前阶段

**阶段 1（MVP）**
- 仅 BTC
- 只做多
- AI 仅做交易过滤

## 回测结果解读建议

- 先看 `summary.json` 的 `go_no_go.checks`，明确哪条门槛没通过。
- 对比 `baseline` 与 `ai_filter_sizing` 的 `max_drawdown_pct` 和 `max_drawdown_recovery_bars`。
- 若交易频率下降但 `expectancy_per_trade` 轻微下降，一般可接受；若明显恶化则需回退参数。
- 必须结合 `segment_metrics.json` 看分段一致性，避免只在单一窗口有效。

## 风险提示

⚠️ **本系统仅供学习研究使用。加密货币交易具有高风险，请勿投入超出承受能力的资金。**

## License

MIT
