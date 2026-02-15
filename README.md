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

### Simplified Telegram Message Format

```

🟡 BTC 觀望訊號 (3/5)

價格資訊
現價: $78,478
入場: $77,500-$78,000
目標: $80,500 (+3.2%)
停損: $76,800 (-2.1%)
風報比: 1:1.5
━━━━━━━━━━━━━━━━
技術指標
RSI 55 | MACD 多頭
恐懼指數: 17/100 (Extreme Fear)
成交量: -65%

機構數據
ETF 淨流: $-493M
多空比: 2.67
━━━━━━━━━━━━━━━━
💡 分析理由
極度恐懼但ETF流出，RSI中性MACD轉多，技術面未破位但機構觀望
📋 倉位管理
20%輕倉試探，分3批進場，每批間隔1H
⚠️ 風險提示
跌破76500確認空頭，目標74000

```

**Message includes:**
- Entry/target/stop with risk-reward ratio
-  Technical indicators with emoji signals
-  Institutional data (ETF flows, long/short ratio)
- AI-synthesized analysis combining all factors
- Position sizing and batch strategy
- Specific price-based risk scenarios

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
