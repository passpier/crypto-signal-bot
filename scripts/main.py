"""Main orchestrator script for crypto signal bot with combined analysis."""
import json
import sys
import logging
import asyncio
import os
import pandas as pd
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

# Detect if running in Google Cloud Run
IS_CLOUD_RUN = os.getenv('K_SERVICE') is not None

# Setup logging - adapt for Cloud Run
if IS_CLOUD_RUN:
    # Cloud Run: Use only StreamHandler (logs go to Cloud Logging)
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
        logger.info("[1/7] Fetching cryptocurrency data from Binance...")
        fetcher = CryptoDataFetcher(
            symbol=config['trading']['symbol']
        )
        df = fetcher.fetch_historical_data(days=30)
        current_price = fetcher.fetch_current_price()
        logger.info(f"✓ Fetched {len(df)} data points | Current: ${current_price['price']:,.2f}")
        
        # ============================================
        # Step 2: Calculate Technical Indicators
        # ============================================
        logger.info("[2/7] Calculating technical indicators (with backtest)...")
        generator = SignalGenerator()
        df = generator.calculate_indicators(df)
        logger.info(f"✓ Technical indicators calculated (RSI, MACD, EMA, Bollinger Bands, OBV)")

        # ============================================
        # Step 7: Run Backtest for Win Rate
        # ============================================
        logger.info("[7/7] Running backtest for historical performance...")
        backtest_stats = None
        try:
            from scripts.backtest import SimpleBacktest
            backtest = SimpleBacktest()
            backtest_stats = backtest.run_backtest(days=30)
            if 'error' not in backtest_stats:
                logger.info(f"✓ Backtest: {backtest_stats.get('win_rate', 0):.1f}% win rate ({backtest_stats.get('total_trades', 0)} trades)")
            else:
                logger.warning(f"⚠ Backtest failed: {backtest_stats.get('error')}")
                backtest_stats = None
        except Exception as e:
            logger.warning(f"⚠ Backtest failed: {e}")
            backtest_stats = None

        # Generate technical signal and strength (quant scoring model)
        tech_signal = generator.calculate_signal_strength(df, backtest_stats=backtest_stats)
        logger.info(f"✓ Technical signal: {tech_signal.get('action')} | Strength: {tech_signal.get('strength')}/5")

        latest = df.iloc[-1]
        
        # ============================================
        # Step 3: Fetch Fear & Greed Index
        # ============================================
        logger.info("[3/7] Fetching Fear & Greed Index (in parallel)...")
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
        logger.info("[4/7] Fetching institutional data (in parallel)...")
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
        logger.info("[5/7] Fetching crypto news (in parallel)...")
        news = []
        try:
            news_fetcher = CryptoNewsFetcher()
            news = news_fetcher.fetch_crypto_news(limit=3)
            logger.info(f"✓ Fetched {len(news)} news articles")
        except Exception as e:
            logger.warning(f"⚠ Failed to fetch crypto news: {e}")

        # Build Telegram payload (no AI dependency)
        telegram_context = {
            'fear_greed_value': fear_greed.get('value') if fear_greed else None,
            'fear_greed_class': fear_greed.get('classification') if fear_greed else None,
            'institutional_summary': {},
            'news_headlines': [n.get('title') for n in news[:3] if n.get('title')] if news else [],
            'technical_summary': {}
        }

        if institutional_data:
            etf_flows = institutional_data.get('etf_flows') or {}
            lsr = institutional_data.get('long_short_ratio') or {}
            funding = institutional_data.get('funding_rate') or {}

            if etf_flows.get('net_flow') is not None:
                telegram_context['institutional_summary']['etf_net_m'] = etf_flows['net_flow'] / 1e6
            if lsr.get('ratio') is not None:
                telegram_context['institutional_summary']['lsr_ratio'] = lsr['ratio']
            if funding.get('rate_pct') is not None:
                telegram_context['institutional_summary']['funding_rate_pct'] = funding['rate_pct']

        # Technical summary for Telegram sentiment block
        telegram_context['technical_summary'] = {
            'rsi': float(latest['rsi']) if pd.notna(latest.get('rsi')) else None,
            'macd': float(latest['macd']) if pd.notna(latest.get('macd')) else None,
            'signal_line': float(latest['signal_line']) if pd.notna(latest.get('signal_line')) else None,
            'volume_change': float(latest['volume_change']) if pd.notna(latest.get('volume_change')) else None
        }
        
        # ============================================
        # Step 6: Analyze Sentiment with AI
        # ============================================
        logger.info("[6/7] Analyzing sentiment with Gemini AI...")
        sentiment = None
        try:
            if fear_greed and len(news) > 0:
                current_price_value = float(current_price['price'])
                sentiment = analyzer.analyze_sentiment_with_ai(
                    fear_greed=fear_greed,
                    news=news,
                    df_with_indicators=df,
                    current_price=current_price_value,
                    institutional_data=institutional_data,
                    tech_signal=tech_signal
                )
                if sentiment and 'ai_advice_text' in sentiment:
                    telegram_context['ai_advice_text'] = sentiment['ai_advice_text']
                logger.info(f"✓ AI sentiment analysis completed | Fear&Greed: {sentiment.get('fear_greed_value', 'N/A')}")
            else:
                logger.warning("⚠ Skipping AI analysis - Fear & Greed data unavailable or news data unavailable")
        except Exception as e:
            logger.warning(f"⚠ AI sentiment analysis failed: {e}")
            logger.warning("  Continuing with technical analysis only...")
        
        # ============================================
        # Step 7: Send Telegram Notification
        # ============================================
        logger.info("[7/7] Processing notification...")
        
        # Build Telegram context (sentiment section)
        # This is now simplified since tech_signal already has all indicators
        telegram_context['backtest_stats'] = backtest_stats
        
        should_notify = True
        
        if should_notify:
            try:
                notifier = TelegramNotifier()
                asyncio.run(notifier.send_signal(
                    signal=tech_signal,
                    sentiment=telegram_context
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
            'signal': tech_signal,
            'fear_greed': {
                'value': fear_greed.get('value') if fear_greed else None,
                'classification': fear_greed.get('classification') if fear_greed else None
            } if fear_greed else None,
            'institutional': {
                'etf_net_flow': institutional_data['etf_flows']['net_flow'] if institutional_data and institutional_data.get('etf_flows') else None,
                'long_short_ratio': institutional_data['long_short_ratio']['ratio'] if institutional_data and institutional_data.get('long_short_ratio') else None,
                'funding_rate_pct': institutional_data['funding_rate']['rate_pct'] if institutional_data and institutional_data.get('funding_rate') else None
            } if institutional_data else None,
            'crypto_news': [n.get('title') for n in news[:3]] if news else [],
            'ai_advice': sentiment.get('ai_advice_text') if sentiment else None,
            'backtest': {
                'win_rate': backtest_stats.get('win_rate') if backtest_stats else None,
                'total_trades': backtest_stats.get('total_trades') if backtest_stats else None,
                'avg_win': backtest_stats.get('avg_win') if backtest_stats else None,
                'avg_loss': backtest_stats.get('avg_loss') if backtest_stats else None
            } if backtest_stats else None,
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
    if not IS_CLOUD_RUN:
        log_dir = get_project_root() / 'logs'
        log_dir.mkdir(exist_ok=True)

    sys.exit(main())
