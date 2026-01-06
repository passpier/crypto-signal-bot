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

### Signal Generation & Strategy

**Technical Signal Calculation (Point-based system -5 to +5):**
- RSI < 30 (oversold): +2 | RSI > 70 (overbought): -2
- MACD golden cross: +2 | MACD death cross: -2
- Price > MA50: +1 | Price < MA50: -1
- Volume > 1.5x average: +1

**Combined with Sentiment (Contrarian Logic):**
| Technical | Sentiment | Result | Logic |
|-----------|-----------|--------|-------|
| BUY | Fear (<40) | 🔥 **STRONG_BUY** | "Buy when others are fearful" |
| BUY | Greed (>60) | ⚠️ BUY (caution) | Potential top, reduce confidence |
| SELL | Greed (>60) | 🔥 **STRONG_SELL** | "Sell when others are greedy" |
| SELL | Fear (<40) | ⚠️ SELL (caution) | Potential bottom, reduce confidence |

**Signal Strength Mapping:**
- **4-5 ⭐ (80-100%)**: Strong signals → Telegram sent
- **3 ⭐ (60%)**: Moderate signals → Telegram sent
- **1-2 ⭐ (<60%)**: Weak/mixed signals → No Telegram sent

### Simplified Telegram Message Format

```
🔔 BTC 強力買入訊號 (4/5)

入場: $89,500-$89,800
現價: $90,316 (-2.42%)
━━━━━━━━━━━━━━━━
目標: $92,500 (+3.2%)
停損: $87,800 (-2.1%)
風報比: 1:1.5
━━━━━━━━━━━━━━━━
訊號依據:
• RSI 28 超賣反彈
• 恐懼指數 29 極度恐懼
• 成交量 +45%

AI風險管理建議:
1. 交易訊號: 分批建倉
2. 訊號強度: 4/5
3. 關鍵因素:
   • RSI超賣區，恐懼指數偏低
4. 風險管理建議: 分2-3批進場，首批40%倉位
5. 主要風險: 若跌破支撐位需及時停損
```

**Message includes:**
- 📊 Entry range and current price
- 🎯 Target and stop loss with percentages
- ⚖️ Risk/reward ratio
- 📈 Signal reasons (technical + sentiment)
- 🤖 **AI風險管理建議** (Gemini output)

## 📋 Prerequisites

### Required
- Python 3.10+ (Anaconda recommended)
- **Telegram Bot Token** - Get from [@BotFather](https://t.me/BotFather)
- **Telegram Chat ID** - Get from [@userinfobot](https://t.me/userinfobot)
- **Google Gemini API Key** - Free tier (1,500/day) from [AI Studio](https://aistudio.google.com/apikey)
- Docker (for n8n automation)

## 💻 Usage

### Setup (First Time)

**1. Install Dependencies**
```bash
cd crypto-signal-bot
pip install -r requirements.txt
```

**2. Configure API Keys**
Edit `config/config.yaml`:
```yaml
api_keys:
  telegram_token: "YOUR_TELEGRAM_BOT_TOKEN"      # From @BotFather
  telegram_chat_id: "YOUR_CHAT_ID"               # From @userinfobot
  gemini_api_key: "YOUR_GEMINI_KEY"              # Optional, from AI Studio
```

**Get Telegram Credentials:**
- Open Telegram → Search **@BotFather** → `/newbot` → Follow instructions
- Search **@userinfobot** → Send any message → Copy your ID

**Get Gemini API Key (Optional):**
- Visit https://aistudio.google.com/apikey → Click "Create API Key"

**3. Test the Bot**
```bash
python tests/test_quick.py           # Quick manual test
python -m unittest discover tests  # Full test suite
python scripts/main.py               # Run live bot
```

### Manual Execution
```bash
# Run full bot (fetch data, generate signal, send to Telegram)
python scripts/main.py

# Test individual components
python scripts/data_fetcher.py      # Test Binance API
python scripts/backtest.py          # 30-day performance
tail -f logs/bot.log                # Monitor logs
```

## ⚙️ Configuration

### Trading Parameters (`config/config.yaml`)
```yaml
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
├── azure_function/              # ☁️ Azure Functions deployment
│   ├── __init__.py              # Timer trigger function
│   ├── function_app.py         # Function app configuration
│   ├── requirements.txt        # Azure Functions dependencies
│   └── host.json               # Host settings
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
