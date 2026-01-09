# 🚀 Crypto Signal Bot

An automated cryptocurrency trading signal bot that combines technical analysis with AI-powered sentiment insights, delivering professional-grade trading signals directly to your Telegram with structured risk management advice.

## ✨ Features

### Core Functionality
- 📊 **Technical Analysis**: RSI, MACD, MA50, MA200 with intelligent trend detection
- 🧠 **Sentiment Analysis**: Fear & Greed Index + Crypto News + CoinGecko data
- 🤖 **AI Synthesis**: Google Gemini combines all data into actionable insights
- 🎯 **Combined Strategy**: Technical + Sentiment = Contrarian trading signals
- 📱 **Enhanced Telegram**: Professional format with complete market context
- 🔄 **Automated Execution**: n8n/cron integration for hourly signal generation
- 📈 **Live Backtesting**: 30-day performance metrics with win rate display
- 💾 **Data Management**: SQLite storage with Binance API integration

## 🏗️ Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                        COMBINED ANALYSIS FLOW                          │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐    │
│  │   BINANCE    │     │  ALTERNATIVE │     │   CRYPTOCOMPARE      │    │
│  │     API      │     │     .ME      │     │       NEWS           │    │
│  │  (Price)     │     │ (Fear&Greed) │     │   (Headlines)        │    │
│  └──────┬───────┘     └──────┬───────┘     └──────────┬───────────┘    │
│         │                    │                        │                │
│         ▼                    ▼                        ▼                │
│  ┌──────────────┐     ┌────────────────────────────────────────┐       │
│  │  TECHNICAL   │     │           SENTIMENT ANALYZER           │       │
│  │   ANALYSIS   │     │   (Fear & Greed + News + CoinGecko)    │       │
│  │              │     └────────────────────────────────────────┘       │
│  │ • RSI        │                      │                               │
│  │ • MACD       │                      ▼                               │
│  │ • MA50/200   │     ┌────────────────────────────────────────┐       │
│  │ • Volume     │     │           GEMINI AI                    │       │
│  └──────┬───────┘     │   (Synthesize all sentiment data)      │       │
│         │             └────────────────────────────────────────┘       │
│         │                              │                               │
│         ▼                              ▼                               │
│  ┌────────────────────────────────────────────────────────────┐        │
│  │                   COMBINED STRATEGY                        │        │
│  │        Technical Signal + Sentiment = Final Decision       │        │
│  └────────────────────────────────────────────────────────────┘        │
│                              │                                         │
│                              ▼                                         │
│  ┌────────────────────────────────────────────────────────────┐        │
│  │                 ENHANCED TELEGRAM MESSAGE                  │        │
│  │   • Price levels • Technical • Sentiment • AI • News       │        │
│  └────────────────────────────────────────────────────────────┘        │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Simplified Telegram Message Format

```
🔔 BTC 買入訊號 (3/5)

入場: $90,334-$90,334
現價: $90,334
━━━━━━━━━━━━━━━━
目標: $95,000 (+5.2%)
停損: $88,000
風報比: 1:1.5
━━━━━━━━━━━━━━━━
RSI 40 | MACD 空頭
恐懼指數: 27/100 (Fear)
成交量 -12%

💡風險管理建議: 使用 10% 的倉位，並在價格回調時分批買入。
⚠️主要風險: 若價格跌破 90,000 美元，可能引發進一步下跌。
關鍵因素:
   • RSI 40 顯示市場超賣，有反彈潛力。
   • 恐懼與貪婪指數 27 處於恐懼區域，情緒上可能觸底。
```

**Message includes:**
- 📊 Entry range and current price
- 🎯 Target and stop loss with percentages
- ⚖️ Risk/reward ratio
- 📈 Signal reasons (technical + sentiment)
- 🤖 Risk management

## 📋 Prerequisites

### Required
- Python 3.11+ (Anaconda recommended)
- **Telegram Bot Token** - Get from [@BotFather](https://t.me/BotFather)
- **Telegram Chat ID** - Get from [@userinfobot](https://t.me/userinfobot)
- **Google Gemini API Key** - Free tier (1,500/day) from [AI Studio](https://aistudio.google.com/apikey)
- Docker (for n8n automation)

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

## ⚙️ Configuration

### Trading Parameters (`config/config.yaml`)
```yaml
api_keys:
  telegram_token: "YOUR_TELEGRAM_BOT_TOKEN"      # From @BotFather
  telegram_chat_id: "YOUR_CHAT_ID"               # From @userinfobot
  gemini_api_key: "YOUR_GEMINI_KEY"              # Optional, from AI Studio

trading:
  symbol: "BTCUSDT"          # Trading pair
  stop_loss_percent: 3       # Default stop loss (%)
  take_profit_percent: 6     # Default take profit (%)
  
indicators:
  rsi_period: 14             # RSI calculation period
  rsi_oversold: 30           # Buy signal threshold
  rsi_overbought: 70         # Sell signal threshold
  macd_fast: 12              # MACD fast EMA
  macd_slow: 26              # MACD slow EMA
  macd_signal: 9             # MACD signal line
```

## 🏗️ Project Structure

```
crypto-signal-bot/
├── scripts/
│   ├── main.py                  # 🎯 Main orchestrator (combined analysis)
│   ├── data_fetcher.py          # 📊 Binance API integration
│   ├── signal_generator.py      # 🔮 Technical analysis (RSI, MACD, MA)
│   ├── sentiment_analyzer.py    # 🧠 Sentiment (Fear&Greed, News, AI)
│   ├── telegram_bot.py          # 📱 Enhanced message format
│   ├── backtest.py              # 📈 30-day performance testing
│   └── utils.py                 # 🛠️ Config & logging
├── config/config.yaml           # ⚙️ Settings & API keys
│── __init__.py                  # Timer trigger function
│── function_app.py              # Function app configuration
│── host.json                    # Host settings
├── .funcignore                  # Deployment exclusions
├── Dockerfile                   # 🐳 Production container
├── docker-compose.prod.yml      # 🚀 Production deployment
├── docker-compose.yml           # 🧪 Development (n8n)
├── tests/
│   ├── test_all.py            # 🧪 All unit tests
│   ├── test_integration.py    # 🔗 Integration tests
│   └── test_quick.py          # ⚡ Quick manual test
└── logs/bot.log               # 📝 Execution logs
```

## 📄 License & Disclaimer

**Educational Use Only**

This bot is for educational and research purposes. Cryptocurrency trading involves substantial risk of loss. The developers assume no responsibility for financial losses. Always:
- Do your own research (DYOR)
- Test thoroughly before real trading
- Understand technical analysis limitations
- Never trade with money you can't afford to lose
