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

        # ADX (Average Directional Index)
        adx_period = self.config['indicators'].get('adx_period', 14)
        high = df['high']
        low = df['low']
        close = df['close']

        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        tr = pd.concat([
            (high - low),
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)

        atr = tr.rolling(window=adx_period, min_periods=adx_period).mean()
        plus_dm_series = pd.Series(plus_dm, index=df.index)
        minus_dm_series = pd.Series(minus_dm, index=df.index)
        plus_di = 100 * plus_dm_series.rolling(window=adx_period, min_periods=adx_period).mean() / atr
        minus_di = 100 * minus_dm_series.rolling(window=adx_period, min_periods=adx_period).mean() / atr
        dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan)
        df['adx'] = dx.rolling(window=adx_period, min_periods=adx_period).mean()
        df['plus_di'] = plus_di
        df['minus_di'] = minus_di

        # Stochastic Oscillator
        stoch_period = self.config['indicators'].get('stoch_period', 14)
        stoch_d_period = self.config['indicators'].get('stoch_d_period', 3)
        low_min = df['low'].rolling(window=stoch_period, min_periods=stoch_period).min()
        high_max = df['high'].rolling(window=stoch_period, min_periods=stoch_period).max()
        stoch_k = 100 * (df['close'] - low_min) / (high_max - low_min)
        df['stoch_k'] = stoch_k.replace([np.inf, -np.inf], np.nan)
        df['stoch_d'] = df['stoch_k'].rolling(window=stoch_d_period, min_periods=stoch_d_period).mean()

        # OBV (On-Balance Volume)
        df['price_change'] = df['close'].diff()
        df['obv'] = (np.where(df['price_change'] > 0, df['volume'],
                             np.where(df['price_change'] < 0, -df['volume'], 0))).cumsum()

        # Volume moving average (20)
        df['volume_ma_20'] = df['volume'].rolling(window=20, min_periods=1).mean()

        # Support level (rolling 20-period low)
        df['support'] = df['low'].rolling(window=20, min_periods=1).min()
        
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

    def calculate_signal_strength(self, df: pd.DataFrame) -> Dict:
        """
        Calculate signal strength and action using a quant scoring model.

        Returns:
            Dictionary with action, strength, score, and derived flags.
        """
        if df is None or df.empty:
            return {'action': 'HOLD', 'strength': 3, 'score': 0}

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        ema_12 = float(latest.get('ema_12', 0) or 0)
        ema_26 = float(latest.get('ema_26', 0) or 0)
        macd = float(latest.get('macd', 0) or 0)
        signal_line = float(latest.get('signal_line', 0) or 0)
        adx = float(latest.get('adx', 0) or 0)
        rsi = float(latest.get('rsi', 50) or 50)
        stoch_k = float(latest.get('stoch_k', 50) or 50)
        stoch_d = float(latest.get('stoch_d', 50) or 50)
        obv = float(latest.get('obv', 0) or 0)
        volume = float(latest.get('volume', 0) or 0)
        volume_ma_20 = float(latest.get('volume_ma_20', 0) or 0)
        support = float(latest.get('support', 0) or 0)
        price = float(latest.get('close', 0) or 0)

        score = 0.0

        # 趨勢指標 (40%)
        if ema_12 > ema_26:
            score += 1
        if macd > signal_line:
            score += 1
        if adx > 25:
            score += 1  # 趨勢強度

        # 動能指標 (30%)
        if rsi <= 30 or rsi >= 70:
            score += 0.5  # 極端值
        if 40 <= rsi <= 60:
            score += 1  # 反轉區
        if stoch_k > stoch_d:
            score += 0.5

        # 量價指標 (20%)
        obv_trend = 'flat'
        if len(df) >= 7:
            obv_prev = float(df.iloc[-7].get('obv', obv) or obv)
            if obv > obv_prev:
                obv_trend = 'up'
            elif obv < obv_prev:
                obv_trend = 'down'
        if obv_trend == 'up':
            score += 1
        if volume_ma_20 > 0 and volume > volume_ma_20 * 1.5:
            score += 0.5

        # 支撐壓力 (10%)
        near_support = False
        bouncing = price > float(prev.get('close', price) or price)
        if support > 0:
            near_support = price <= support * 1.01
        if near_support and bouncing:
            score += 0.5

        # 標準化到 1-5
        strength = round(score / 2) + 1
        strength = max(1, min(5, int(strength)))

        # Directional bias for action
        direction_score = 0
        direction_score += 1 if ema_12 > ema_26 else -1
        direction_score += 1 if macd > signal_line else -1
        if rsi <= 30:
            direction_score += 1
        elif rsi >= 70:
            direction_score -= 1
        if stoch_k > stoch_d:
            direction_score += 1
        elif stoch_k < stoch_d:
            direction_score -= 1
        if obv_trend == 'up':
            direction_score += 1
        elif obv_trend == 'down':
            direction_score -= 1

        if direction_score >= 2 and strength >= 3:
            action = 'BUY'
        elif direction_score <= -2 and strength >= 3:
            action = 'SELL'
        else:
            action = 'HOLD'

        return {
            'action': action,
            'strength': strength,
            'score': score,
            'obv_trend': obv_trend,
            'near_support': near_support,
            'bouncing': bouncing
        }


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
