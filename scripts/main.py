"""Main orchestrator script for crypto signal bot with combined analysis."""
import json
import sys
import logging
import asyncio
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.data_fetcher import CryptoDataFetcher
from scripts.signal_generator import SignalGenerator
from scripts.telegram_bot import TelegramNotifier
from scripts.sentiment_analyzer import SentimentAnalyzer
from scripts.utils import get_project_root, validate_config, load_config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
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
        # Step 2: Generate Technical Signal
        # ============================================
        logger.info("[2/6] Calculating technical indicators...")
        generator = SignalGenerator()
        df = generator.calculate_indicators(df)
        signal = generator.generate_signal(df)
        logger.info(f"✓ Technical Signal: {signal['action']} (strength: {signal['strength']}/5)")
        
        # ============================================
        # Step 3: Fetch Sentiment Analysis
        # ============================================
        logger.info("[3/6] Analyzing market sentiment...")
        sentiment = None
        try:
            analyzer = SentimentAnalyzer()
            sentiment = analyzer.get_full_sentiment_analysis(signal)
            logger.info(f"✓ Sentiment: {sentiment.get('sentiment_class', 'N/A')} | Fear&Greed: {sentiment.get('fear_greed_value', 'N/A')}")
            logger.info(f"✓ Consistency: {sentiment.get('consistency', 'N/A')}")
        except Exception as e:
            logger.warning(f"⚠ Sentiment analysis failed: {e}")
            logger.warning("  Continuing with technical analysis only...")
        
        # ============================================
        # Step 4: Run Backtest for Win Rate
        # ============================================
        logger.info("[4/6] Running backtest for historical performance...")
        backtest_stats = None
        try:
            from scripts.backtest import SimpleBacktest
            backtest = SimpleBacktest()
            backtest_stats = backtest.run_backtest(days=30)
            logger.info(f"✓ Backtest: {backtest_stats.get('win_rate', 0):.1f}% win rate ({backtest_stats.get('total_trades', 0)} trades)")
        except Exception as e:
            logger.warning(f"⚠ Backtest failed: {e}")
        
        # ============================================
        # Step 5: Determine if Signal Warrants Notification
        # ============================================
        logger.info("[5/6] Evaluating signal strength for notification...")
        
        # Decide whether to send notification
        should_notify = False
        notification_reason = ""
        
        if signal['action'] != 'HOLD':
            should_notify = True
            notification_reason = f"Technical {signal['action']} signal (strength {signal['strength']}/5)"
        elif sentiment:
            # Check if sentiment provides strong directional signal
            consistency = sentiment.get('consistency', '')
            recommendation = sentiment.get('recommendation', '')
            fear_greed_value = sentiment.get('fear_greed_value', 50)
            
            # Contrarian logic: Extreme Fear/Greed can override neutral technical signals
            if fear_greed_value <= 25:  # Extreme Fear - contrarian BUY opportunity
                should_notify = True
                notification_reason = f"Contrarian BUY: Extreme Fear ({fear_greed_value}) + Neutral Technical"
            elif fear_greed_value >= 75:  # Extreme Greed - contrarian SELL opportunity
                should_notify = True
                notification_reason = f"Contrarian SELL: Extreme Greed ({fear_greed_value}) + Neutral Technical"
            elif consistency in ['一致看多', '一致看空']:
                should_notify = True
                notification_reason = f"Sentiment consistency: {consistency}"
            elif recommendation in ['積極買入', '立即止損']:
                should_notify = True
                notification_reason = f"AI recommendation: {recommendation}"
        
        if should_notify:
            logger.info(f"✓ Notification triggered: {notification_reason}")
        else:
            logger.info("✓ No clear signal - skipping notification")
        
        # ============================================
        # Step 6: Send Enhanced Telegram Notification
        # ============================================
        logger.info("[6/6] Processing notification...")
        
        if should_notify:
            try:
                notifier = TelegramNotifier()
                asyncio.run(notifier.send_signal(
                    signal=signal,
                    sentiment=sentiment,
                    backtest_stats=backtest_stats
                ))
                logger.info("✓ Enhanced signal sent to Telegram!")
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
            'action': signal['action'],
            'strength': signal['strength'],
            'price': signal['price'],
            'technical': {
                'rsi': signal['indicators'].get('rsi'),
                'macd': signal['indicators'].get('macd'),
                'price_change_24h': signal['indicators'].get('price_change_24h')
            },
            'sentiment': {
                'fear_greed': sentiment.get('fear_greed_value') if sentiment else None,
                'sentiment_class': sentiment.get('sentiment_class') if sentiment else None,
                'consistency': sentiment.get('consistency') if sentiment else None,
                'recommendation': sentiment.get('recommendation') if sentiment else None
            } if sentiment else None,
            'backtest': {
                'win_rate': backtest_stats.get('win_rate') if backtest_stats else None,
                'total_trades': backtest_stats.get('total_trades') if backtest_stats else None
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
    # Ensure logs directory exists
    log_dir = get_project_root() / 'logs'
    log_dir.mkdir(exist_ok=True)
    
    sys.exit(main())
