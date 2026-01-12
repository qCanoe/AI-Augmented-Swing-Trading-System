# AI Trading System

AI-Augmented Swing Trading System for BTC/ETH (3–7 day holding period, low leverage)

## Project Overview

This system combines **traditional technical indicators** with **general-purpose large language models (LLM) for real-time analysis**. The core goal is to **reduce drawdowns, filter out low-quality trades, and improve risk-adjusted returns**.

### Core Design Principles

- Indicators are responsible for "discovering opportunities", AI is responsible for "vetoing and adjusting"
- AI does not directly place orders, only outputs structured recommendations
- All trades must pass hard risk control rules
- The system supports safe degradation when AI is unavailable

## Quick Start

### 1. Environment Setup

```bash
# Clone the repository
git clone <repo-url>
cd AI-Trading

# Create virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# Install dependencies
pip install -e .
# Or development mode
pip install -e ".[dev]"
```

### 2. Configuration

```bash
# Copy example configuration
cp config.example.env .env

# Edit .env and fill in your API keys
```

### 3. Run

```bash
# Single run (fetch data → decision → execute/record)
python -m ai_trading.main --once

# Loop run (every 15 minutes)
python -m ai_trading.main --loop --interval-min 15

# View help
python -m ai_trading.main --help
```

## Project Structure

```
AI-Trading/
├── pyproject.toml          # Project configuration and dependencies
├── config.example.env       # Configuration example
├── README.md                # This file
├── Framework.md             # System design documentation
├── data/                    # Data storage directory
│   └── journal/            # Trading logs (JSONL)
└── src/ai_trading/         # Source code
    ├── main.py             # CLI entry point
    ├── config.py           # Configuration loading
    ├── data/               # Data collection
    │   └── binance.py      # Binance data interface
    ├── features/           # Feature calculation
    │   └── indicators.py   # Technical indicators
    ├── strategy/           # Strategy module
    │   └── candidates.py   # Candidate trade generation
    ├── ai/                 # AI module
    │   ├── openrouter_client.py  # OpenRouter client
    │   └── schemas.py      # Input/output schemas
    ├── risk/               # Risk control module
    │   └── rules.py        # Hard risk control rules
    ├── exec/               # Execution module
    │   ├── paper.py        # Paper trading
    │   └── binance_live.py # Live execution
    ├── journal/            # Logging module
    │   └── store.py        # Trade record storage
    └── utils/              # Utility module
        └── logging.py      # Structured logging
```

## Current Stage

**Stage 1 (MVP)**
- BTC only
- Long positions only
- AI only filters trades

## Risk Warning

⚠️ **This system is for educational and research purposes only. Cryptocurrency trading carries high risks. Please do not invest more than you can afford to lose.**

## License

MIT
