"""Signal generation module using technical indicators."""
import pandas as pd
import numpy as np
from typing import Dict, Optional
import logging
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.utils import load_config, get_project_root

logger = logging.getLogger(__name__)


class SignalGenerator:
    """Generates trading signals based on technical indicators and AI analysis."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize signal generator.
        
        Args:
            config_path: Path to config file. Defaults to config/config.yaml
        """
        self.config = load_config(config_path)
        logger.info("Signal generator initialized (technical analysis only)")
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate technical indicators.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added indicator columns
        """
        df = df.copy()
        
        # Ensure we have enough data
        if len(df) < 200:
            logger.warning(f"Limited data points ({len(df)}). Some indicators may be NaN.")
        
        # RSI calculation
        rsi_period = self.config['indicators'].get('rsi_period', 14)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD calculation
        macd_fast = self.config['indicators'].get('macd_fast', 12)
        macd_slow = self.config['indicators'].get('macd_slow', 26)
        macd_signal = self.config['indicators'].get('macd_signal', 9)
        
        exp1 = df['close'].ewm(span=macd_fast, adjust=False).mean()
        exp2 = df['close'].ewm(span=macd_slow, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['signal_line'] = df['macd'].ewm(span=macd_signal, adjust=False).mean()
        df['macd_histogram'] = df['macd'] - df['signal_line']
        
        # EMA (Exponential Moving Average) - using 12 and 26 periods
        ema_period_short = self.config['indicators'].get('ema_short', 12)
        ema_period_long = self.config['indicators'].get('ema_long', 26)
        df['ema_12'] = df['close'].ewm(span=ema_period_short, adjust=False).mean()
        df['ema_26'] = df['close'].ewm(span=ema_period_long, adjust=False).mean()
        
        # Bollinger Bands
        bb_period = self.config['indicators'].get('bb_period', 20)
        bb_std = self.config['indicators'].get('bb_std', 2)
        df['bb_middle'] = df['close'].rolling(window=bb_period).mean()
        bb_std_val = df['close'].rolling(window=bb_period).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std_val * bb_std)
        df['bb_lower'] = df['bb_middle'] - (bb_std_val * bb_std)
        
        # OBV (On-Balance Volume)
        df['price_change'] = df['close'].diff()
        df['obv'] = (np.where(df['price_change'] > 0, df['volume'],
                             np.where(df['price_change'] < 0, -df['volume'], 0))).cumsum()
        
        # Volume change percentage (7-day average)
        df['volume_change'] = 0.0
        if len(df) >= 7:
            # Calculate rolling 7-day average volume
            volume_avg_7d = df['volume'].rolling(window=7, min_periods=1).mean()
            # Calculate volume change percentage vs 7-day average
            df['volume_change'] = ((df['volume'] / volume_avg_7d) - 1) * 100
            # Replace inf/nan with 0 and clamp extreme values
            df['volume_change'] = df['volume_change'].replace([np.inf, -np.inf, np.nan], 0.0)
            # Clamp to reasonable range (-100% to +1000%) to prevent extreme values
            df['volume_change'] = df['volume_change'].clip(lower=-100, upper=1000)
        
        return df


# Test
if __name__ == "__main__":
    import sys
    from scripts.data_fetcher import CryptoDataFetcher
    
    logging.basicConfig(level=logging.INFO)
    
    try:
        fetcher = CryptoDataFetcher()
        df = fetcher.fetch_historical_data(days=30)
        
        generator = SignalGenerator()
        df_with_indicators = generator.calculate_indicators(df)
        
        latest = df_with_indicators.iloc[-1]
        print(f"Latest indicators calculated:")
        print(f"RSI: {latest.get('rsi', 'N/A')}")
        print(f"MACD: {latest.get('macd', 'N/A')}")
        print(f"EMA12: {latest.get('ema_12', 'N/A')}")
        print(f"EMA26: {latest.get('ema_26', 'N/A')}")
        print(f"BB Upper: {latest.get('bb_upper', 'N/A')}")
        print(f"BB Middle: {latest.get('bb_middle', 'N/A')}")
        print(f"BB Lower: {latest.get('bb_lower', 'N/A')}")
        print(f"OBV: {latest.get('obv', 'N/A')}")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)

