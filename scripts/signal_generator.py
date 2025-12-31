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
        
        # Moving averages
        df['ma_50'] = df['close'].rolling(window=50).mean()
        df['ma_200'] = df['close'].rolling(window=200).mean()
        
        return df
    
    def generate_signal(self, df: pd.DataFrame) -> Dict:
        """
        Generate trading signal based on technical indicators and AI analysis.
        
        Args:
            df: DataFrame with calculated indicators
            
        Returns:
            Dictionary with signal information
        """
        if len(df) < 2:
            raise ValueError("Insufficient data to generate signal. Need at least 2 data points.")
        
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        
        # Initialize signal strength and reasons
        signal_strength = 0
        reasons = []
        
        # RSI analysis
        rsi_oversold = self.config['indicators'].get('rsi_oversold', 30)
        rsi_overbought = self.config['indicators'].get('rsi_overbought', 70)
        
        if pd.notna(latest['rsi']):
            if latest['rsi'] < rsi_oversold:
                signal_strength += 2
                reasons.append(f"RSI {latest['rsi']:.1f} 超賣反彈")
            elif latest['rsi'] > rsi_overbought:
                signal_strength -= 2
                reasons.append(f"RSI {latest['rsi']:.1f} 超買回調")
        
        # MACD analysis
        if pd.notna(latest['macd']) and pd.notna(latest['signal_line']):
            if pd.notna(prev['macd']) and pd.notna(prev['signal_line']):
                # Golden cross
                if latest['macd'] > latest['signal_line'] and prev['macd'] <= prev['signal_line']:
                    signal_strength += 2
                    reasons.append("MACD黃金交叉")
                # Death cross
                elif latest['macd'] < latest['signal_line'] and prev['macd'] >= prev['signal_line']:
                    signal_strength -= 2
                    reasons.append("MACD死亡交叉")
        
        # Moving average analysis
        if pd.notna(latest['ma_50']):
            if latest['close'] > latest['ma_50']:
                signal_strength += 1
                reasons.append("價格突破MA50")
            elif latest['close'] < latest['ma_50']:
                signal_strength -= 1
        
        # Volume analysis
        if len(df) >= 7:
            volume_avg = df['volume'].tail(7).mean()
            if volume_avg > 0 and pd.notna(latest['volume']):
                volume_change = (latest['volume'] / volume_avg - 1) * 100
                if latest['volume'] > volume_avg * 1.5:
                    signal_strength += 1
                    reasons.append(f"成交量放大 {volume_change:.0f}%")
        
        # Determine action first (needed for summary generation)
        if signal_strength >= 3:
            action = 'BUY'
        elif signal_strength <= -3:
            action = 'SELL'
        else:
            action = 'HOLD'
        
        # Generate technical summary
        technical_summary = self._generate_technical_summary(action, signal_strength, latest)
        
        # Calculate entry, stop loss, and take profit
        entry_price = float(latest['close'])
        stop_loss_percent = self.config['trading']['stop_loss_percent']
        take_profit_percent = self.config['trading']['take_profit_percent']
        
        stop_loss = entry_price * (1 - stop_loss_percent / 100)
        take_profit = entry_price * (1 + take_profit_percent / 100)
        
        # Calculate risk-reward ratio
        risk = entry_price - stop_loss
        reward = take_profit - entry_price
        risk_reward = reward / risk if risk > 0 else 0
        
        # Calculate volume change percentage
        volume_change = 0
        if len(df) >= 7:
            volume_avg = df['volume'].tail(7).mean()
            if volume_avg > 0:
                volume_change = (latest['volume'] / volume_avg - 1) * 100
        
        # Calculate 24h price change
        price_change_24h = 0
        if len(df) >= 24:
            price_24h_ago = df.iloc[-24]['close']
            price_change_24h = ((entry_price / price_24h_ago) - 1) * 100
        
        return {
            'action': action,
            'strength': min(abs(signal_strength), 5),
            'signal_score': signal_strength,  # Raw score for combined analysis
            'price': entry_price,
            'entry_range': (entry_price * 0.99, entry_price * 1.01),
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'risk_reward': risk_reward,
            'reasons': reasons if reasons else ["無明顯訊號"],
            'technical_summary': technical_summary,
            'indicators': {
                'rsi': float(latest['rsi']) if pd.notna(latest['rsi']) else None,
                'macd': float(latest['macd']) if pd.notna(latest['macd']) else None,
                'macd_histogram': float(latest['macd_histogram']) if pd.notna(latest.get('macd_histogram')) else None,
                'ma_50': float(latest['ma_50']) if pd.notna(latest.get('ma_50')) else None,
                'ma_200': float(latest['ma_200']) if pd.notna(latest.get('ma_200')) else None,
                'volume_change': volume_change,
                'price_change_24h': price_change_24h
            }
        }
    
    def _generate_technical_summary(self, action: str, strength: int, latest: pd.Series) -> str:
        """Generate a technical analysis summary without AI."""
        rsi = latest.get('rsi')
        macd = latest.get('macd')
        
        summaries = {
            'BUY': [
                "技術面轉強，多項指標顯示買入訊號",
                "RSI 與 MACD 同步看漲，趨勢向上",
                "價格突破關鍵均線，動能增強"
            ],
            'SELL': [
                "技術面轉弱，多項指標顯示賣出訊號",
                "RSI 與 MACD 同步看跌，趨勢向下",
                "價格跌破關鍵支撐，注意風險"
            ],
            'HOLD': [
                "技術指標混合，建議觀望等待",
                "趨勢不明確，等待更好進場點",
                "盤整階段，耐心等待方向突破"
            ]
        }
        
        import random
        base = random.choice(summaries.get(action, summaries['HOLD']))
        
        # Add specific context
        if rsi is not None and pd.notna(rsi):
            if rsi < 30:
                base += f"，RSI {rsi:.0f} 超賣"
            elif rsi > 70:
                base += f"，RSI {rsi:.0f} 超買"
        
        return base


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
        signal = generator.generate_signal(df_with_indicators)
        
        print(f"訊號: {signal['action']} ({'⭐' * signal['strength']})")
        print(f"價格: ${signal['price']:,.2f}")
        print(f"建議進場: ${signal['entry_range'][0]:,.0f} - ${signal['entry_range'][1]:,.0f}")
        print(f"停損: ${signal['stop_loss']:,.2f}")
        print(f"目標: ${signal['take_profit']:,.2f}")
        print(f"風報比: 1:{signal['risk_reward']:.1f}")
        print(f"\n理由:")
        for reason in signal['reasons']:
            print(f"  • {reason}")
        print(f"\nAI分析: {signal['ai_analysis']}")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)

