"""Main orchestrator script for crypto signal bot with combined analysis."""
import json
import sys
import logging
import asyncio
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.data_fetcher import CryptoDataFetcher
from scripts.signal_generator import SignalGenerator
from scripts.telegram_bot import TelegramNotifier
from scripts.sentiment_analyzer import SentimentAnalyzer
from scripts.utils import get_project_root, validate_config, load_config
from scripts.coinglass_fetcher import CoinglassFetcher
from scripts.crypto_news_fetcher import CryptoNewsFetcher
# Detect if running in Azure Functions
IS_AZURE_FUNCTIONS = os.getenv('FUNCTIONS_WORKER_RUNTIME') is not None or \
                     os.getenv('WEBSITE_INSTANCE_ID') is not None

# Setup logging - adapt for Azure Functions
if IS_AZURE_FUNCTIONS:
    # Azure Functions: Use only StreamHandler (logs go to Application Insights)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
else:
    # Local/Docker: Use file and stream handlers
    log_dir = get_project_root() / 'logs'
    log_dir.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / 'bot.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )

logger = logging.getLogger(__name__)


def main():
    """
    Main execution function with combined technical + sentiment analysis.
    
    Flow:
    1. Fetch price data from Binance
    2. Calculate technical indicators (RSI, MACD, MA)
    3. Generate technical signal (BUY/SELL/HOLD)
    4. Fetch sentiment data (Fear & Greed, News, Market Data)
    5. Use Gemini AI to synthesize sentiment analysis
    6. Combine technical + sentiment for final recommendation
    7. Send enhanced Telegram notification
    """
    try:
        # Validate configuration
        config = load_config()
        if not validate_config(config):
            logger.error("Configuration validation failed. Please check your config.yaml or environment variables.")
            sys.exit(1)
        
        logger.info("=" * 60)
        logger.info("Starting Crypto Signal Bot (Combined Analysis Mode)")
        logger.info("=" * 60)
        
        # ============================================
        # Step 1: Fetch Price Data from Binance
        # ============================================
        logger.info("[1/6] Fetching cryptocurrency data from Binance...")
        fetcher = CryptoDataFetcher(
            symbol=config['trading']['symbol']
        )
        df = fetcher.fetch_historical_data(days=30)
        current_price = fetcher.fetch_current_price()
        logger.info(f"✓ Fetched {len(df)} data points | Current: ${current_price['price']:,.2f}")
        
        # ============================================
        # Step 2: Calculate Technical Indicators
        # ============================================
        logger.info("[2/7] Calculating technical indicators...")
        generator = SignalGenerator()
        df = generator.calculate_indicators(df)
        logger.info(f"✓ Technical indicators calculated (RSI, MACD, EMA, Bollinger Bands, OBV)")
        
        # ============================================
        # Step 3: Fetch Fear & Greed Index
        # ============================================
        logger.info("[3/7] Fetching Fear & Greed Index...")
        analyzer = SentimentAnalyzer()
        fear_greed = None
        try:
            fear_greed = analyzer.fetch_fear_greed_index()
            logger.info(f"✓ Fear & Greed Index: {fear_greed.get('value', 'N/A')} ({fear_greed.get('classification', 'N/A')})")
        except Exception as e:
            logger.warning(f"⚠ Failed to fetch Fear & Greed Index: {e}")
        

        # ============================================
        # Step 4: Fetch Institutional Data (Coinglass)
        # ============================================
        logger.info("[4/7] Fetching institutional data from Coinglass...")
        institutional_data = None
        try:
            cg_fetcher = CoinglassFetcher()
            institutional_data = cg_fetcher.fetch_all_institutional_data(
                symbol=config['trading']['symbol'].replace('USDT', '')
            )
            logger.info(f"✓ Institutional data fetched")
        except Exception as e:
            logger.warning(f"⚠ Failed to fetch Coinglass data: {e}")

        # ============================================
        # Step 5: Fetch Crypto News
        # ============================================
        logger.info("[5/7] Fetching crypto news...")
        news = []
        try:
            news_fetcher = CryptoNewsFetcher()
            news = news_fetcher.fetch_crypto_news(limit=3)
            logger.info(f"✓ Fetched {len(news)} news articles")
        except Exception as e:
            logger.warning(f"⚠ Failed to fetch crypto news: {e}")
        
        # ============================================
        # Step 6: Analyze Sentiment with AI
        # ============================================
        logger.info("[6/7] Analyzing sentiment with AI...")
        sentiment = None
        try:
            if fear_greed:
                current_price_value = float(current_price['price'])
                sentiment = analyzer.analyze_sentiment_with_ai(
                    fear_greed=fear_greed,
                    news=news,
                    df_with_indicators=df,
                    current_price=current_price_value,
                    institutional_data=institutional_data 
                )
                sentiment['news_headlines'] = [n['title'] for n in news[:3]]
                logger.info(f"✓ AI sentiment analysis completed | Fear&Greed: {sentiment.get('fear_greed_value', 'N/A')}")
            else:
                logger.warning("⚠ Skipping AI analysis - Fear & Greed data unavailable")
        except Exception as e:
            logger.warning(f"⚠ AI sentiment analysis failed: {e}")
            logger.warning("  Continuing with technical analysis only...")
        
        # ============================================
        # Step 7: Run Backtest for Win Rate
        # ============================================
        logger.info("[7/7] Running backtest for historical performance...")
        #todo: add backtest and fix logic later

        # backtest_stats = None
        # try:
        #     from scripts.backtest import SimpleBacktest
        #     backtest = SimpleBacktest()
        #     backtest_stats = backtest.run_backtest(days=30)
        #     logger.info(f"✓ Backtest: {backtest_stats.get('win_rate', 0):.1f}% win rate ({backtest_stats.get('total_trades', 0)} trades)")
        # except Exception as e:
        #     logger.warning(f"⚠ Backtest failed: {e}")
        
        # ============================================
        # Step 8: Send Telegram Notification
        # ============================================
        logger.info("[7/7] Processing notification...")
        
        # Create minimal signal dict from DataFrame for Telegram bot compatibility
        import pandas as pd
        latest = df.iloc[-1]
        current_price_value = float(current_price['price'])
        
        signal_dict = {
            'action': 'HOLD',  # AI will determine action
            'strength': 3,
            'price': current_price_value,
            'indicators': {
                'rsi': float(latest['rsi']) if pd.notna(latest.get('rsi')) else None,
                'macd': float(latest['macd']) if pd.notna(latest.get('macd')) else None,
                'ema_12': float(latest['ema_12']) if pd.notna(latest.get('ema_12')) else None,
                'bb_upper': float(latest['bb_upper']) if pd.notna(latest.get('bb_upper')) else None,
                'bb_middle': float(latest['bb_middle']) if pd.notna(latest.get('bb_middle')) else None,
                'bb_lower': float(latest['bb_lower']) if pd.notna(latest.get('bb_lower')) else None,
                'obv': float(latest['obv']) if pd.notna(latest.get('obv')) else None,
                'volume_change': float(latest['volume_change']) if pd.notna(latest.get('volume_change')) else 0.0
            }
        }
        
        should_notify = True
        
        if should_notify:
            try:
                notifier = TelegramNotifier()
                asyncio.run(notifier.send_signal(
                    signal=signal_dict,
                    sentiment=sentiment,
                ))
                logger.info("✓ Signal sent to Telegram!")
            except Exception as e:
                logger.error(f"✗ Failed to send Telegram notification: {e}")
        else:
            logger.info("✓ Holding - no notification sent")
        
        # ============================================
        # Output Summary
        # ============================================
        logger.info("=" * 60)
        logger.info("EXECUTION SUMMARY")
        logger.info("=" * 60)
        
        output = {
            'action': 'HOLD',  # Determined by AI analysis
            'price': current_price_value,
            'technical': {
                'rsi': signal_dict['indicators'].get('rsi'),
                'macd': signal_dict['indicators'].get('macd'),
                'ema_12': signal_dict['indicators'].get('ema_12'),
                'volume_change': signal_dict['indicators'].get('volume_change')
            },
            'institutional': {
                'etf_net_flow': institutional_data['etf_flows']['net_flow'] if institutional_data and institutional_data.get('etf_flows') else None,
                'long_short_ratio': institutional_data['long_short_ratio']['ratio'] if institutional_data and institutional_data.get('long_short_ratio') else None
            } if institutional_data else None,
            'sentiment': {
                'fear_greed': sentiment.get('fear_greed_value') if sentiment else None,
                'ai_advice': sentiment.get('ai_advice_text') if sentiment else None
            } if sentiment else None,
            # 'backtest': {
            #     'win_rate': backtest_stats.get('win_rate') if backtest_stats else None,
            #     'total_trades': backtest_stats.get('total_trades') if backtest_stats else None
            # } if backtest_stats else None,
            'notification_sent': should_notify,
            'timestamp': str(df.iloc[-1]['timestamp']) if 'timestamp' in df.columns else None
        }
        
        print(json.dumps(output, indent=2, ensure_ascii=False))
        
        logger.info("=" * 60)
        logger.info("Bot execution completed successfully")
        logger.info("=" * 60)
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Bot execution failed: {e}", exc_info=True)
        print(json.dumps({'error': str(e), 'action': 'ERROR'}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    # Ensure logs directory exists (only for local execution)
    if not IS_AZURE_FUNCTIONS:
        log_dir = get_project_root() / 'logs'
        log_dir.mkdir(exist_ok=True)
    
    sys.exit(main())
