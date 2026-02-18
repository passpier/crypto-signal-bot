# 🚀 Crypto Signal Bot

An automated cryptocurrency trading signal bot that combines **technical analysis**, **institutional data**, and **AI-powered sentiment insights**, delivering professional-grade swing trading signals directly to your Telegram with structured risk management advice.

## ✨ Features

### Core Functionality
- **Technical Analysis**: RSI, MACD, EMA, Bollinger Bands, OBV with intelligent trend detection
- 🏦 **Institutional Data**: ETF flows, long/short ratio, funding rates (Coinglass + Binance)
- 🧠 **Sentiment Analysis**: Fear & Greed Index + Crypto News aggregation
- 🤖 **AI Synthesis**: Google Gemini 2.5 Flash Lite combines all data into actionable insights
- 🎯 **Combined Strategy**: Technical + Institutional + Sentiment = High-conviction signals
- 📱 **Enhanced Telegram**: Professional format with emoji indicators and complete market context
- 🔄 **Automated Execution**: Scheduled via cron/Azure Functions for hands-free operation
- 💾 **Data Management**: SQLite storage with Binance API integration

## 🏗️ Architecture Overview

```

┌────────────────────────────────────────────────────────────────────────────┐
│                         MULTI-LAYER ANALYSIS FLOW                          │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌────────────┐   │
│  │   BINANCE    │   │    BITBO     │   │  ALTERNATIVE │   │ CRYPTOCOMP │   │
│  │     API      │   │  (ETF Flows) │   │     .ME      │   │    NEWS    │   │
│  │  (OHLCV)     │   │ +Binance LSR │   │(Fear\&Greed) │   │(Headlines) │   │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────┬─────┘   │
│         │                  │                  │                  │         │
│         ▼                  ▼                  ▼                  ▼         │
│  ┌──────────────┐   ┌───────────────────┐   ┌─────────────────────────┐    │
│  │  TECHNICAL   │   │  INSTITUTIONAL    │   │   SENTIMENT ANALYZER    │    │
│  │   ANALYSIS   │   │     DATA          │   │ (Fear\&Greed + News)    │    │
│  │              │   │                   │   └─────────────────────────┘    │
│  │ -  RSI       │   │ -  ETF Net Flow   │              │                   │
│  │ -  MACD      │   │ -  Long/Short     │              ▼                   │
│  │ -  EMA 12/50 │   │ -  Funding Rate   │   ┌─────────────────────────┐    │
│  │ -  Bollinger │   │                   │   │      GEMINI AI          │    │
│  │ -  OBV       │   └─────────┬─────────┘   │ (Synthesize all data)   │    │
│  └──────┬───────┘             │             └─────────────────────────┘    │
│         │                     │                        │                   │
│         └─────────────────────┴────────────────────────┘                   │
│                               │                                            │
│                               ▼                                            │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                    AI-POWERED COMBINED STRATEGY                    │    │
│  │  Technical (trend) + Institutional (smart money) + Sentiment       │    │
│  │  (crowd psychology) = High-conviction swing trade signals          │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                               │                                            │
│                               ▼                                            │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │              FORMATTED TELEGRAM NOTIFICATION                       │    │
│  │        Prices - Indicators - Institutional - Analysis              │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘

```

## 🎯 Why This Combined Analysis Works

### The Three-Layer Intelligence System

#### Layer 1: Technical Analysis (What)
**Identifies WHERE price is relative to historical patterns**
- RSI/MACD: Overbought/oversold momentum
- EMA: Trend direction and support/resistance
- Bollinger Bands: Volatility and price extremes
- OBV: Volume confirmation

**Limitation**: Technical indicators lag and produce false signals in choppy markets (~60% accuracy alone)

#### Layer 2: Institutional Data (Who)
**Reveals WHO is moving the market (smart money)**
- **ETF Flows**: Real institutional buy/sell pressure (e.g., -$494M = bearish)
- **Long/Short Ratio**: Retail positioning (contrarian indicator when extreme)
- **Funding Rate**: Cost of holding perpetual futures (>0.1% = overheated)

**Why Critical**: Retail follows technicals, institutions CREATE trends. ETF flows predict medium-term direction better than any indicator.

**Example**: 
- Technical says "oversold, buy here"
- But ETF flows show -$800M outflow → Institutions disagree
- **Correct action**: Wait or light position (not full buy)

#### Layer 3: Sentiment Analysis (Why)
**Captures crowd psychology and news catalysts**
- **Fear & Greed Index**: Extreme fear (<25) often marks bottoms; extreme greed (>75) marks tops
- **News Headlines**: Regulatory changes, hacks, institutional adoption
- **Contrarian Signal**: When everyone is fearful + technicals oversold + institutions buying = strong buy

**Why It Works**: Markets are driven by human emotions. Panic selling creates opportunity; euphoria creates risk.

### Telegram Message Example

```

🟢 BTC 買入  ★★★★★ (5/5)
💰 現價: $78,478  |  ATR 2.3%
─────────────────
▸ 入場  $77,800 – $78,200  (保守優先)
▸ 停損  $75,500  ← 硬停損
▸ 目標  T1 $82,000  RR 1.6  |  T2 $86,000  RR 3.2  |  T3 $91,000
▸ 倉位  10.0%  (Kelly: 12.3%)
─────────────────
📌 理由: 技術指標（RSI、MACD、OBV）普遍偏空，但ETF資金流入顯示機構看多
─────────────────
技術指標
【趨勢】EMA 多頭排列 | ADX 28.3 (強趨勢)
【動能】RSI 22 (超賣) | 隨機 28↘35 (死叉)
【位置】布林 中軌 | 支撐 76,500 | 壓力 81,000
【量能】成交量 +45% | OBV 上升
─────────────────
市場情緒
Fear & Greed  17/100 — Extreme Fear
ETF 淨流 +320M  |  多空比 0.85  |  Funding +0.010%

• Bitcoin faces macro headwinds...
• Institutional ETF inflows hit weekly high
─────────────────
🤖 AI 分析
理由: ...narrative only, no duplicate fields...

```

## 📋 Prerequisites

### Required
- Python 3.11+ (Anaconda recommended)
- **Telegram Bot Token** - Get from [@BotFather](https://t.me/BotFather)
- **Telegram Chat ID** - Get from [@userinfobot](https://t.me/userinfobot)
- **Google Gemini API Key** - Free tier (1,500/day) from [AI Studio](https://aistudio.google.com/apikey)

## 💻 Usage

### Setup

**1. Install Dependencies**
```bash
cd crypto-signal-bot
pip install -r requirements.txt
```

**2. Test Locally**
```bash
python tests/test_quick.py           # Quick manual test
python -m unittest discover tests  # Full test suite
python scripts/main.py               # Run live bot
```

## 📄 License & Disclaimer

**Educational Use Only**

This bot is for educational and research purposes. Cryptocurrency trading involves substantial risk of loss. The developers assume no responsibility for financial losses. Always:
- Do your own research (DYOR)
- Test thoroughly before real trading
- Understand technical analysis limitations
- Never trade with money you can't afford to lose
