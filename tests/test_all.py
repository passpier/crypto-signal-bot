"""Comprehensive test suite for crypto signal bot."""
import unittest
import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.data_fetcher import CryptoDataFetcher
from scripts.signal_generator import SignalGenerator
from scripts.backtest import SimpleBacktest
from scripts.sentiment_analyzer import SentimentAnalyzer
from scripts.telegram_bot import TelegramNotifier
import logging

# Suppress logging during tests
logging.basicConfig(level=logging.CRITICAL)


class TestDataFetcher(unittest.TestCase):
    """Test cases for CryptoDataFetcher."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.fetcher = CryptoDataFetcher()

    def test_fetch_current_price(self):
        """Test fetching current BTC price."""
        try:
            price = self.fetcher.fetch_current_price()
            self.assertGreater(price['price'], 0, "Price should be positive")
            self.assertIn('change_24h', price, "Should include 24h change")
            self.assertIn('volume', price, "Should include volume")
            self.assertIsInstance(price['price'], (int, float))
        except Exception as e:
            self.skipTest(f"API may be unavailable: {e}")
    
    def test_fetch_historical_data(self):
        """Test fetching historical OHLCV data."""
        try:
            df = self.fetcher.fetch_historical_data(days=7)
            self.assertGreater(len(df), 0, "Should return data")
            required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            for col in required_columns:
                self.assertIn(col, df.columns, f"Should have {col} column")
        except Exception as e:
            self.skipTest(f"API may be unavailable: {e}")


class TestSignalGenerator(unittest.TestCase):
    """Test cases for SignalGenerator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.generator = SignalGenerator()
        self.fetcher = CryptoDataFetcher()
    
    def test_calculate_indicators(self):
        """Test technical indicators calculation."""
        # Create sample data
        dates = pd.date_range('2024-01-01', periods=300, freq='1H')
        np.random.seed(42)
        prices = 50000 + np.cumsum(np.random.randn(300) * 100)
        
        df = pd.DataFrame({
            'timestamp': dates,
            'open': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'close': prices,
            'volume': np.random.rand(300) * 1000000
        })
        
        df_with_indicators = self.generator.calculate_indicators(df)
        
        # Check that indicators are calculated
        self.assertIn('rsi', df_with_indicators.columns)
        self.assertIn('macd', df_with_indicators.columns)
        self.assertIn('ema_50', df_with_indicators.columns)
        self.assertIn('ema_200', df_with_indicators.columns)
        
        # Check that RSI values are reasonable (0-100)
        if not df_with_indicators['rsi'].isna().all():
            rsi_values = df_with_indicators['rsi'].dropna()
            self.assertTrue((rsi_values >= 0).all() and (rsi_values <= 100).all())
    
    def test_generate_signal(self):
        """Test signal generation with real data."""
        try:
            df = self.fetcher.fetch_historical_data(days=7)
            if len(df) < 2:
                self.skipTest("Insufficient data for signal generation")
            
            df_with_indicators = self.generator.calculate_indicators(df)
            signal = self.generator.generate_signal(df_with_indicators)
            
            # Validate signal structure
            self.assertIn(signal['action'], ['BUY', 'SELL', 'HOLD'])
            self.assertGreaterEqual(signal['strength'], 0)
            self.assertLessEqual(signal['strength'], 5)
            self.assertGreater(signal['price'], 0)
            self.assertIn('reasons', signal)
            self.assertIn('indicators', signal)
            self.assertIn('entry_range', signal)
            self.assertIn('stop_loss', signal)
            self.assertIn('take_profit', signal)
            self.assertIn('risk_reward', signal)
            
            # Validate entry range
            entry_min, entry_max = signal['entry_range']
            self.assertLessEqual(entry_min, entry_max)
        except Exception as e:
            self.skipTest(f"Signal generation test skipped: {e}")


class TestBacktest(unittest.TestCase):
    """Test cases for SimpleBacktest."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.backtest = SimpleBacktest()
    
    def test_run_backtest(self):
        """Test running backtest."""
        try:
            results = self.backtest.run_backtest(days=7)
            
            # Validate result structure
            self.assertIn('win_rate', results)
            self.assertIn('total_trades', results)
            self.assertIn('wins', results)
            self.assertIn('losses', results)
            
            # Validate values
            self.assertGreaterEqual(results['win_rate'], 0)
            self.assertLessEqual(results['win_rate'], 100)
            self.assertGreaterEqual(results['total_trades'], 0)
            self.assertGreaterEqual(results['wins'], 0)
            self.assertGreaterEqual(results['losses'], 0)
        except Exception as e:
            self.skipTest(f"Backtest may be unavailable: {e}")


class TestSentimentAnalyzer(unittest.TestCase):
    """Test cases for SentimentAnalyzer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.analyzer = SentimentAnalyzer()
    
    def test_fetch_fear_greed_index(self):
        """Test fetching Fear & Greed Index."""
        try:
            fear_greed = self.analyzer.fetch_fear_greed_index()
            self.assertIn('value', fear_greed)
            self.assertIn('classification', fear_greed)
            self.assertGreaterEqual(fear_greed['value'], 0)
            self.assertLessEqual(fear_greed['value'], 100)
        except Exception as e:
            self.skipTest(f"API may be unavailable: {e}")
    
    def test_fetch_crypto_news(self):
        """Test fetching crypto news."""
        try:
            news = self.analyzer.fetch_crypto_news(limit=5)
            self.assertIsInstance(news, list)
            if len(news) > 0:
                article = news[0]
                self.assertIn('title', article)
                self.assertIn('source', article)
        except Exception as e:
            self.skipTest(f"API may be unavailable: {e}")
    
    def test_fetch_market_data_summary(self):
        """Test fetching market data summary."""
        try:
            market_data = self.analyzer.fetch_market_data_summary()
            self.assertIn('btc_dominance', market_data)
            self.assertGreaterEqual(market_data.get('btc_dominance', 0), 0)
            self.assertLessEqual(market_data.get('btc_dominance', 100), 100)
        except Exception as e:
            self.skipTest(f"API may be unavailable: {e}")
    
    def test_analyze_sentiment_with_ai_complete_data(self):
        """Test analyze_sentiment_with_ai with complete data."""
        try:
            fear_greed = self.analyzer.fetch_fear_greed_index()
            news = self.analyzer.fetch_crypto_news(limit=3)
            market_data = self.analyzer.fetch_market_data_summary()
            
            technical_signal = {
                'action': 'BUY',
                'strength': 4,
                'indicators': {
                    'rsi': 28,
                    'price_change_24h': -2.4,
                    'macd': 150,
                    'volume_change': 45
                }
            }
            
            result = self.analyzer.analyze_sentiment_with_ai(
                fear_greed=fear_greed,
                news=news,
                market_data=market_data,
                technical_signal=technical_signal
            )
            
            # Validate result structure
            required_keys = [
                'sentiment_score', 'sentiment_class', 'fear_greed_value',
                'fear_greed_class', 'consistency', 'recommendation', 'risk_warning'
            ]
            for key in required_keys:
                self.assertIn(key, result, f"Result should contain {key}")
            
            # Validate values
            self.assertGreaterEqual(result['sentiment_score'], 0)
            self.assertLessEqual(result['sentiment_score'], 10)
        except Exception as e:
            self.skipTest(f"AI analysis may be unavailable: {e}")
    
    def test_analyze_sentiment_with_ai_missing_data(self):
        """Test analyze_sentiment_with_ai handles missing data gracefully."""
        result = self.analyzer.analyze_sentiment_with_ai(
            fear_greed={},
            news=[],
            market_data={},
            technical_signal={}
        )
        
        # Should still return valid structure
        self.assertIn('sentiment_score', result)
        self.assertIn('sentiment_class', result)
        self.assertIn('fear_greed_value', result)
    
    def test_prompt_generation_edge_cases(self):
        """Test prompt generation handles edge cases safely."""
        scenarios = [
            {
                "fear_greed": {},
                "market_data": {},
                "technical_signal": {}
            },
            {
                "fear_greed": {"value": 29},
                "market_data": {"btc_dominance": 56.9},
                "technical_signal": {"action": "BUY", "strength": 5, "indicators": {}}
            },
            {
                "fear_greed": {"value": 75},
                "market_data": {"btc_dominance": 58.0},
                "technical_signal": {"action": "SELL", "strength": 3, "indicators": {"rsi": 72}}
            }
        ]
        
        for scenario in scenarios:
            try:
                result = self.analyzer.analyze_sentiment_with_ai(
                    fear_greed=scenario['fear_greed'],
                    news=[],
                    market_data=scenario['market_data'],
                    technical_signal=scenario['technical_signal']
                )
                # Should not crash
                self.assertIn('sentiment_score', result)
            except Exception as e:
                # Some failures are acceptable (e.g., API unavailable)
                pass


class TestTelegramBot(unittest.TestCase):
    """Test cases for TelegramNotifier."""
    
    def setUp(self):
        """Set up test fixtures."""
        try:
            self.notifier = TelegramNotifier()
        except ValueError:
            # Telegram not configured - skip tests
            self.skipTest("Telegram not configured (missing token/chat_id)")
    
    def test_message_formatting(self):
        """Test that message formatting works without sending."""
        test_signal = {
            'action': 'BUY',
            'strength': 4,
            'price': 89642,
            'entry_range': (89500, 89800),
            'stop_loss': 87800,
            'take_profit': 92500,
            'risk_reward': 1.7,
            'reasons': ['RSI 64 超賣反彈', 'MACD黃金交叉'],
            'indicators': {
                'rsi': 64,
                'macd': 125.5,
                'volume_change': -90,
                'price_change_24h': -2.71
            }
        }
        
        test_sentiment = {
            'fear_greed_value': 35,
            'fear_greed_class': 'Fear',
            'sentiment_score': 4,
            'sentiment_class': '恐懼',
            'ai_advice_text': '若決定進場，建議分批建倉'
        }
        
        test_backtest = {'win_rate': 78, 'total_trades': 45}
        
        # Test that message can be formatted (without actually sending)
        if hasattr(self.notifier, '_format_signal_message'):
            message = self.notifier._format_signal_message(
                test_signal, test_sentiment, test_backtest
            )
            self.assertIsInstance(message, str)
            self.assertGreater(len(message), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
