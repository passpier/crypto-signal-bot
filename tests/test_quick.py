#!/usr/bin/env python3
"""Quick manual test script for the crypto signal bot."""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.data_fetcher import CryptoDataFetcher
from scripts.signal_generator import SignalGenerator
import logging

logging.basicConfig(level=logging.INFO)

def main():
    """Quick test of basic bot functionality."""
    print("🚀 Quick Bot Test")
    print("=" * 50)
    
    try:
        # Test data fetching
        fetcher = CryptoDataFetcher()
        current = fetcher.fetch_current_price()
        print(f"✅ BTC Price: ${current['price']:,.2f} ({current['change_24h']:+.2f}%)")
        
        # Test signal generation
        df = fetcher.fetch_historical_data(days=7)
        generator = SignalGenerator()
        df_with_indicators = generator.calculate_indicators(df)
        signal = generator.generate_signal(df_with_indicators)
        
        print(f"✅ Signal: {signal['action']} (strength: {signal['strength']}/5)")
        print(f"✅ Entry: ${signal['entry_range'][0]:,.0f}-${signal['entry_range'][1]:,.0f}")
        print(f"✅ Stop Loss: ${signal['stop_loss']:,.0f}")
        print(f"✅ Take Profit: ${signal['take_profit']:,.0f}")
        
        return 0
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

