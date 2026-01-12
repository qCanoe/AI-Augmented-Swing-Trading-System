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
python -m ai_trading.main --once

# 循环运行（每15分钟一轮）
python -m ai_trading.main --loop --interval-min 15

# 查看帮助
python -m ai_trading.main --help
```

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

## 风险提示

⚠️ **本系统仅供学习研究使用。加密货币交易具有高风险，请勿投入超出承受能力的资金。**

## License

MIT
