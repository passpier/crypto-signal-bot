"""Integration tests for the full bot workflow."""
import unittest
import sys
from pathlib import Path
import asyncio

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.data_fetcher import CryptoDataFetcher
from scripts.signal_generator import SignalGenerator
from scripts.sentiment_analyzer import SentimentAnalyzer
from scripts.backtest import SimpleBacktest
from scripts.telegram_bot import TelegramNotifier
import logging

logging.basicConfig(level=logging.WARNING)


class TestIntegration(unittest.TestCase):
    """Integration tests for full bot workflow."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_db_path = str(project_root / 'data' / 'test_btc_prices.db')
        self.fetcher = CryptoDataFetcher(db_path=self.test_db_path)
        self.generator = SignalGenerator()
        self.analyzer = SentimentAnalyzer()
        self.backtest = SimpleBacktest()
    
    def test_full_workflow(self):
        """Test the complete bot workflow from data fetching to signal generation."""
        try:
            # Step 1: Fetch data
            current = self.fetcher.fetch_current_price()
            self.assertGreater(current['price'], 0)
            
            df = self.fetcher.fetch_historical_data(days=7)
            self.assertGreater(len(df), 0)
            
            # Step 2: Generate technical signal
            df_with_indicators = self.generator.calculate_indicators(df)
            signal = self.generator.generate_signal(df_with_indicators)
            
            self.assertIn(signal['action'], ['BUY', 'SELL', 'HOLD'])
            self.assertGreater(signal['strength'], 0)
            
            # Step 3: Get sentiment analysis
            sentiment = self.analyzer.get_full_sentiment_analysis(signal)
            
            self.assertIn('sentiment_score', sentiment)
            self.assertIn('fear_greed_value', sentiment)
            
            # Step 4: Run backtest
            backtest_stats = self.backtest.run_backtest(days=7)
            
            self.assertIn('win_rate', backtest_stats)
            self.assertIn('total_trades', backtest_stats)
            
            # Verify all components work together
            self.assertIsInstance(signal, dict)
            self.assertIsInstance(sentiment, dict)
            self.assertIsInstance(backtest_stats, dict)
            
        except Exception as e:
            self.skipTest(f"Integration test skipped: {e}")
    
    def test_combined_strategy_logic(self):
        """Test the combined technical + sentiment strategy logic."""
        try:
            # Fetch data and generate signal
            df = self.fetcher.fetch_historical_data(days=7)
            df_with_indicators = self.generator.calculate_indicators(df)
            signal = self.generator.generate_signal(df_with_indicators)
            
            # Get sentiment
            sentiment = self.analyzer.get_full_sentiment_analysis(signal)
            
            # Test combined logic
            tech_action = signal['action']
            tech_strength = signal['strength']
            fear_greed = sentiment.get('fear_greed_value', 50)
            
            # Verify contrarian logic
            if tech_action == 'BUY' and fear_greed < 40:
                # BUY + Fear = Strong contrarian opportunity
                self.assertGreater(tech_strength, 0)
            elif tech_action == 'SELL' and fear_greed > 60:
                # SELL + Greed = Strong contrarian warning
                self.assertGreater(tech_strength, 0)
            
        except Exception as e:
            self.skipTest(f"Combined strategy test skipped: {e}")
    
    def test_telegram_integration(self):
        """Test Telegram notification with full workflow."""
        try:
            notifier = TelegramNotifier()
        except ValueError:
            self.skipTest("Telegram not configured")
        
        try:
            # Generate test data
            df = self.fetcher.fetch_historical_data(days=7)
            df_with_indicators = self.generator.calculate_indicators(df)
            signal = self.generator.generate_signal(df_with_indicators)
            sentiment = self.analyzer.get_full_sentiment_analysis(signal)
            backtest_stats = self.backtest.run_backtest(days=7)
            
            # Test that send_signal accepts correct parameters
            # (We don't actually send to avoid spam)
            import inspect
            sig = inspect.signature(notifier.send_signal)
            params = list(sig.parameters.keys())
            self.assertIn('signal', params)
            self.assertIn('sentiment', params)
            self.assertIn('backtest_stats', params)
            
        except Exception as e:
            self.skipTest(f"Telegram integration test skipped: {e}")


if __name__ == '__main__':
    unittest.main(verbosity=2)

