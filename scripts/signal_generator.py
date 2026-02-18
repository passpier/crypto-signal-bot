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
        # Note: For 1H data, 200 candles is ~8.3 days.
        if len(df) < 50:
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

        # EMA-50 and EMA-200 for trend analysis
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()

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
        df['atr'] = atr  # Store ATR in DataFrame
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

        # Resistance level (rolling 20-period high)
        df['resistance'] = df['high'].rolling(window=20, min_periods=1).max()

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

    def calculate_signal_strength(self, df: pd.DataFrame, backtest_stats: Optional[Dict] = None) -> Dict:
        """
        Professional-grade signal calculator with entry/exit prices and risk management.

        Args:
            df: DataFrame with calculated indicators
            backtest_stats: Optional backtest statistics for real win rate calculation

        Returns:
            Comprehensive trading plan with entries, exits, position sizing, and risk metrics.
        """
        if df is None or df.empty:
            return {
                'action': 'HOLD', 
                'strength': 3, 
                'score': 0,
                'trade_plan': None
            }

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        # Extract all indicators
        ema_12 = float(latest.get('ema_12', 0) or 0)
        ema_26 = float(latest.get('ema_26', 0) or 0)
        ema_50 = float(latest.get('ema_50', 0) or 0)
        ema_200 = float(latest.get('ema_200', 0) or 0)
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
        resistance = float(latest.get('resistance', 0) or 0)
        price = float(latest.get('close', 0) or 0)
        high = float(latest.get('high', price) or price)
        low = float(latest.get('low', price) or price)
        atr = float(latest.get('atr', 0) or 0)
        bb_upper = float(latest.get('bb_upper', 0) or 0)
        bb_middle = float(latest.get('bb_middle', 0) or 0)
        bb_lower = float(latest.get('bb_lower', 0) or 0)

        # Weights
        WEIGHTS = {
            'trend': 0.35,
            'momentum': 0.30,
            'volume': 0.25,
            'technical': 0.10
        }

        # ============================================
        # 1. TREND SCORE (0-100)
        # ============================================
        trend_score = 0
        
        if ema_12 > ema_26:
            trend_score += 25
        if ema_12 > ema_50:
            trend_score += 15
        if ema_50 > ema_200:
            trend_score += 10
        
        if macd > signal_line:
            trend_score += 25
        
        if adx > 25:
            trend_score += 25
        elif adx > 20:
            trend_score += 12.5

        # ============================================
        # 2. MOMENTUM SCORE (0-100)
        # ============================================
        momentum_score = 0
        
        if 30 < rsi < 40:
            momentum_score += 50
        elif 60 < rsi < 70:
            momentum_score += 25
        elif rsi <= 30:
            momentum_score += 35
        elif rsi >= 70:
            momentum_score += 10
        elif 40 <= rsi <= 60:
            momentum_score += 40

        if stoch_k > stoch_d and stoch_k < 80:
            momentum_score += 30
        elif stoch_k < stoch_d and stoch_k > 20:
            momentum_score += 15
        
        macd_hist = macd - signal_line
        if len(df) > 1:
            prev_macd = float(prev.get('macd', 0) or 0)
            prev_signal = float(prev.get('signal_line', 0) or 0)
            prev_hist = prev_macd - prev_signal
            if macd_hist > prev_hist and macd_hist > 0:
                momentum_score += 20
            elif macd_hist < prev_hist and macd_hist < 0:
                momentum_score += 10

        # ============================================
        # 3. VOLUME SCORE (0-100)
        # ============================================
        volume_score = 0
        
        # High volatility / Panic adjustments
        is_panic = False
        if price > 0 and pd.notna(atr):
             atr_percent_val = (atr / price * 100)
             # Require BOTH high volatility AND extreme RSI, OR extremely high volatility
             is_panic = (atr_percent_val > 3.0 and (rsi < 30 or rsi > 70)) or (atr_percent_val > 5.0)
        else:
             is_panic = False # Default to false if no ATR
        
        obv_trend = 'flat'
        if len(df) >= 20:
            obv_ma = df['obv'].rolling(20).mean().iloc[-1]
            if obv > obv_ma * 1.02:
                obv_trend = 'up'
                volume_score += 50
            elif obv < obv_ma * 0.98:
                obv_trend = 'down'
                volume_score += 20
            else:
                volume_score += 30
        
        if volume_ma_20 > 0:
            if volume > volume_ma_20 * 1.5:
                volume_score += 30
            elif volume > volume_ma_20 * 1.2:
                volume_score += 20
            else:
                volume_score += 10
        
        if len(df) >= 10:
            price_ma = df['close'].rolling(10).mean().iloc[-1]
            price_trend_up = price > price_ma
            if obv_trend == 'down' and price_trend_up:
                volume_score -= 20
            elif obv_trend == 'up' and not price_trend_up:
                volume_score -= 10

        # ============================================
        # 4. TECHNICAL SCORE (0-100)
        # ============================================
        technical_score = 0
        atr_percent = 0 # Initialize here
        
        near_support = False
        near_resistance = False
        bouncing = price > float(prev.get('close', price) or price)
        
        if support > 0:
            near_support = price <= support * 1.005
            if near_support and bouncing:
                technical_score += 50
            elif near_support:
                technical_score += 30
        
        if resistance > 0:
            near_resistance = price >= resistance * 0.995
            if near_resistance and not bouncing:
                technical_score += 20
        
        if support > 0 and resistance > 0:
            range_size = resistance - support
            if range_size > 0:
                position = (price - support) / range_size
                if 0.2 <= position <= 0.4:
                    technical_score += 30
                elif 0.6 <= position <= 0.8:
                    technical_score += 15
        
        if price > 0 and pd.notna(atr):
            atr_percent = (atr / price * 100)
            if atr_percent > 2.0:
                technical_score += 20
            elif atr_percent > 1.0:
                technical_score += 15

        # ============================================
        # 5. WEIGHTED TOTAL SCORE
        # ============================================
        total_score = (
            trend_score * WEIGHTS['trend'] +
            momentum_score * WEIGHTS['momentum'] +
            volume_score * WEIGHTS['volume'] +
            technical_score * WEIGHTS['technical']
        )
        
        total_score = max(0, min(100, total_score))
        
        # ============================================
        # 6. RISK ADJUSTMENT
        # ============================================
        risk_factor = 1.0
        
        # In panic mode, we want to trade the volatility, not penalize it
        if not is_panic:
             if volume_ma_20 > 0 and volume < volume_ma_20 * 0.5:
                risk_factor *= 0.8
        
             if adx < 15:
                risk_factor *= 0.85
        
             if atr_percent > 5.0:
                risk_factor *= 0.75
        else:
             # In panic mode, slightly boost risk factor for opportunities
             risk_factor *= 1.2
        
        adjusted_score = total_score * risk_factor
        
        # ============================================
        # 7. STRENGTH RATING
        # ============================================
        if adjusted_score >= 80:
            strength = 5
        elif adjusted_score >= 65:
            strength = 4
        elif adjusted_score >= 50:
            strength = 3
        elif adjusted_score >= 35:
            strength = 2
        else:
            strength = 1
        
        # ============================================
        # 8. DIRECTIONAL BIAS
        # ============================================
        direction_score = 0
        
        if ema_12 > ema_26:
            direction_score += 1
        else:
            direction_score -= 1
        
        if macd > signal_line:
            direction_score += 1
        else:
            direction_score -= 1
        
        if rsi <= 35:
            direction_score += 1
        elif rsi >= 65:
            direction_score -= 1
        
        if stoch_k > stoch_d:
            direction_score += 1
        else:
            direction_score -= 1
        
        if obv_trend == 'up':
            direction_score += 1
        elif obv_trend == 'down':
            direction_score -= 1
        
        if near_support and bouncing:
            direction_score += 1
        elif near_resistance and not bouncing:
            direction_score -= 1
        
        # ============================================
        # 9. ACTION DECISION
        # ============================================
        action = 'HOLD'
        min_volatility = 0.5
        
        # Panic Strategy: Relax requirements for high volatility opportunities
        strength_threshold = 3 if is_panic else 4
        direction_threshold = 2 if is_panic else 3
        
        if direction_score >= direction_threshold and strength >= strength_threshold and atr_percent >= min_volatility:
            action = 'BUY'
        elif direction_score <= -direction_threshold and strength >= strength_threshold and atr_percent >= min_volatility:
            action = 'SELL'
        
        # Original logic as fallback/conservative
        elif direction_score >= 4 and strength >= 3:
            action = 'BUY'
        elif direction_score <= -4 and strength >= 3:
            action = 'SELL'
            
        # Panic Reversal Logic (Catch the knife with confirmation)
        if is_panic and action == 'HOLD':
             # Oversold bounce - Require RSI < 25 (deeper) and stronger bounce
             if rsi < 25 and price > float(latest.get('open', price)) and price > float(prev.get('close', price)):
                 action = 'BUY'
                 strength = 4
                 logger.info("Panic Buy Triggered: Deep Oversold Bounce")
             # Overbought dump - Require RSI > 75 (higher) and stronger dump
             elif rsi > 75 and price < float(latest.get('open', price)) and price < float(prev.get('close', price)):
                 action = 'SELL'
                 strength = 4
                 logger.info("Panic Sell Triggered: Extreme Overbought Dump")
        
        if action == 'BUY' and near_resistance and not is_panic:
            action = 'HOLD'
        elif action == 'SELL' and near_support and bouncing and not is_panic:
            action = 'HOLD'
        
        # ============================================
        # 10. 🎯 PROFESSIONAL TRADE PLAN
        # ============================================
        trade_plan = None
        
        if action in ['BUY', 'SELL']:
            trade_plan = self._calculate_trade_plan(
                action=action,
                strength=strength,
                price=price,
                atr=atr,
                support=support,
                resistance=resistance,
                bb_upper=bb_upper,
                bb_middle=bb_middle,
                bb_lower=bb_lower,
                rsi=rsi,
                adx=adx,
                df=df,
                backtest_stats=backtest_stats
            )
        
        return {
            'action': action,
            'strength': strength,
            'price': price,
            'score': round(adjusted_score, 2),
            'raw_score': round(total_score, 2),
            'direction_score': direction_score,
            'obv_trend': obv_trend,
            'near_support': near_support,
            'near_resistance': near_resistance,
            'bouncing': bouncing,
            'atr_percent': round(atr_percent, 2),
            'component_scores': {
                'trend': round(trend_score, 1),
                'momentum': round(momentum_score, 1),
                'volume': round(volume_score, 1),
                'technical': round(technical_score, 1)
            },
            'indicators': {
                'ema_12': ema_12,
                'ema_26': ema_26,
                'ema_50': ema_50,
                'ema_200': ema_200,
                'adx': adx,
                'rsi': rsi,
                'stoch_k': stoch_k,
                'stoch_d': stoch_d,
                'bb_upper': bb_upper,
                'bb_middle': bb_middle,
                'bb_lower': bb_lower,
                'support': support,
                'resistance': resistance,
                'atr': atr,
                'obv': obv,
                'volume': volume,
                'volume_ma_20': volume_ma_20,
                'volume_change': float(latest.get('volume_change', 0) or 0)
            },
            'trade_plan': trade_plan
        }


    def _calculate_trade_plan(self, action, strength, price, atr, support, resistance,
                            bb_upper, bb_middle, bb_lower, rsi, adx, df, backtest_stats=None) -> Dict:
        """
        Calculate comprehensive trade plan with entries, exits, and risk management.
        
        Returns detailed trading blueprint including:
        - Multiple entry zones (aggressive/conservative)
        - Multiple profit targets (T1/T2/T3)
        - Stop loss levels (hard/trailing)
        - Position sizing recommendations
        - Risk-reward ratios
        - Expected holding period
        - Market regime classification
        """
        
        # ============================================
        # A. 市場型態分類 (Market Regime)
        # ============================================
        # 為什麼：不同市況用不同策略
        
        regime = 'ranging'  # 預設盤整
        
        if adx > 30:
            regime = 'trending_strong'  # 強趨勢
        elif adx > 20:
            regime = 'trending_weak'   # 弱趨勢
        
        # 波動率分類
        atr_percent = (atr / price * 100) if price > 0 else 0
        if atr_percent > 4:
            volatility = 'high'
        elif atr_percent > 2:
            volatility = 'medium'
        else:
            volatility = 'low'
        
        # ============================================
        # B. ATR倍數設定 (根據市況調整)
        # ============================================
        # 為什麼：趨勢市場給更大空間，盤整縮小風險
        
        if regime == 'trending_strong':
            stop_atr_multiplier = 2.5    # 強趨勢給2.5ATR停損
            target_atr_multipliers = [3, 5, 8]  # 目標更遠
        elif regime == 'trending_weak':
            stop_atr_multiplier = 2.0
            target_atr_multipliers = [2, 4, 6]
        else:  # ranging
            stop_atr_multiplier = 1.5    # 盤整縮小停損
            target_atr_multipliers = [1.5, 3, 4]  # 目標更近
        
        # 高波動額外放寬
        if volatility == 'high':
            stop_atr_multiplier *= 1.2
        
        # ============================================
        # C. 做多計劃 (LONG)
        # ============================================
        if action == 'BUY':
            
            # ----------------
            # 1. 入場價格
            # ----------------
            entries = {
                'aggressive': price,  # 激進：市價單
                'conservative': None,  # 保守：等回測
                'ideal': None,  # 理想：最佳位置
                'limit_order': None  # 掛單價
            }
            
            # 保守入場：等回測到支撐或布林中軌
            if bb_middle > 0 and price > bb_middle:
                entries['conservative'] = round(bb_middle, 2)
            elif support > 0:
                entries['conservative'] = round(support * 1.005, 2)  # 支撐上0.5%
            else:
                entries['conservative'] = round(price * 0.985, 2)  # 回調1.5%
            
            # 理想入場：結合技術位和ATR
            if support > 0 and bb_lower > 0:
                entries['ideal'] = round(max(support, bb_lower), 2)
            elif support > 0:
                entries['ideal'] = round(support, 2)
            elif bb_lower > 0:
                entries['ideal'] = round(bb_lower, 2)
            else:
                entries['ideal'] = round(price - atr * 0.5, 2)
            
            # 掛單建議
            entries['limit_order'] = entries['conservative']
            
            # ----------------
            # 2. 停損價格
            # ----------------
            stops = {
                'hard_stop': None,      # 硬停損（絕不能跌破）
                'soft_stop': None,      # 軟停損（可容忍假跌破）
                'trailing_stop': None,  # 移動停損啟動價
                'mental_stop': None     # 心理停損（檢討出場價）
            }
            
            # 硬停損：ATR法
            stops['hard_stop'] = round(price - atr * stop_atr_multiplier, 2)
            
            # 如果有支撐，取較低者
            if support > 0:
                support_stop = round(support * 0.995, 2)  # 支撐下0.5%
                stops['hard_stop'] = max(stops['hard_stop'], support_stop)
            
            # 軟停損：給一點喘息空間
            stops['soft_stop'] = round(stops['hard_stop'] * 0.99, 2)
            
            # 移動停損：獲利10%後啟動
            stops['trailing_stop'] = round(price * 1.10, 2)
            
            # 心理停損：虧損超過5%就該檢討
            stops['mental_stop'] = round(price * 0.95, 2)
            
            # ----------------
            # 3. 獲利目標
            # ----------------
            targets = {
                'T1': None,  # 第一目標（獲利了結1/3）
                'T2': None,  # 第二目標（獲利了結1/3）
                'T3': None,  # 第三目標（全出or留底倉）
                'moon': None  # 夢想價（大行情才能到）
            }
            
            # ATR法計算目標
            targets['T1'] = round(price + atr * target_atr_multipliers[0], 2)
            targets['T2'] = round(price + atr * target_atr_multipliers[1], 2)
            targets['T3'] = round(price + atr * target_atr_multipliers[2], 2)
            
            # 如果有壓力位，調整T1
            if resistance > 0 and resistance < targets['T1']:
                targets['T1'] = round(resistance * 0.995, 2)  # 壓力前止盈
            
            # 布林上軌作為參考
            if bb_upper > 0:
                targets['moon'] = round(bb_upper, 2)
            else:
                targets['moon'] = round(price * 1.20, 2)  # +20%
            
            # ----------------
            # 4. 風險報酬比 (Risk-Reward Ratio)
            # ----------------
            risk = price - stops['hard_stop']
            reward_T1 = targets['T1'] - price
            reward_T2 = targets['T2'] - price
            reward_T3 = targets['T3'] - price
            
            rr_ratios = {
                'T1': round(reward_T1 / risk, 2) if risk > 0 else 0,
                'T2': round(reward_T2 / risk, 2) if risk > 0 else 0,
                'T3': round(reward_T3 / risk, 2) if risk > 0 else 0,
            }
            
            # ----------------
            # 5. 倉位建議 (Position Sizing)
            # ----------------
            # 凱利公式簡化版：f = (勝率 × 報酬 - 敗率) / 報酬

            # Use actual backtest data if available
            kelly_source = "強度估算 (無回測)"
            if backtest_stats and backtest_stats.get('win_rate') and backtest_stats.get('avg_win') and backtest_stats.get('avg_loss'):
                actual_win_rate = backtest_stats['win_rate'] / 100
                avg_win = backtest_stats['avg_win']
                avg_loss = abs(backtest_stats['avg_loss'])

                if avg_loss > 0:
                    b = avg_win / avg_loss  # Reward/Risk ratio
                    kelly_fraction = (actual_win_rate * b - (1 - actual_win_rate)) / b
                else:
                    kelly_fraction = 0.10  # Default if no losses

                kelly_source = f"回測勝率 {backtest_stats['win_rate']:.1f}%"
            else:
                # Fallback to strength-based estimates
                win_rate_map = {5: 0.65, 4: 0.58, 3: 0.52, 2: 0.48, 1: 0.42}
                estimated_win_rate = win_rate_map.get(strength, 0.50)

                if rr_ratios['T2'] > 0:
                    kelly_fraction = (estimated_win_rate * rr_ratios['T2'] - (1 - estimated_win_rate)) / rr_ratios['T2']
                else:
                    kelly_fraction = 0

            # LOW-RISK BTC: Half-Kelly with 15% hard cap
            kelly_fraction = max(0, min(kelly_fraction * 0.5, 0.15))

            position_sizing = {
                'kelly_fraction': round(kelly_fraction, 3),  # 凱利建議
                'conservative': round(kelly_fraction * 0.5, 3),  # 半凱利
                'aggressive': round(kelly_fraction * 1.5, 3),  # 1.5倍凱利
                'max_risk_percent': 1.5,  # 單筆最大風險1.5%（低風險BTC）
                'recommended': None,
                'kelly_source': kelly_source  # Track data source
            }
            
            # 根據強度決定
            if strength >= 4:
                position_sizing['recommended'] = position_sizing['aggressive']
            elif strength == 3:
                position_sizing['recommended'] = position_sizing['kelly_fraction']
            else:
                position_sizing['recommended'] = position_sizing['conservative']
            
            # 安全檢查
            position_sizing['recommended'] = min(position_sizing['recommended'], 0.25)
            
            # ----------------
            # 6. 加碼計劃 (Pyramiding)
            # ----------------
            pyramiding = {
                'enabled': strength >= 4 and regime == 'trending_strong',
                'add_on_levels': [],
                'reduce_size_by': 0.5  # 每次加碼減半
            }
            
            if pyramiding['enabled']:
                # 獲利5%, 10%, 15%時加碼
                pyramiding['add_on_levels'] = [
                    round(price * 1.05, 2),
                    round(price * 1.10, 2),
                    round(price * 1.15, 2)
                ]
            
            # ----------------
            # 7. 持有週期預估
            # ----------------
            # 根據ATR和目標距離估算
            if atr > 0:
                days_to_T1 = abs(targets['T1'] - price) / atr
                days_to_T2 = abs(targets['T2'] - price) / atr
            else:
                days_to_T1 = 5
                days_to_T2 = 10
            
            holding_period = {
                'min_days': max(1, int(days_to_T1 * 0.5)),  # 最快
                'expected_days': int(days_to_T1),  # 預期
                'max_days': int(days_to_T2),  # 最慢
                'regime_factor': regime  # 趨勢市場持有更久
            }
            
            # ----------------
            # 8. 出場策略
            # ----------------
            exit_strategy = {
                'T1_action': 'SELL_33%',  # 到T1賣1/3
                'T2_action': 'SELL_33%',  # 到T2賣1/3
                'T3_action': 'SELL_REMAINING_OR_TRAIL',  # 到T3全出或留底倉追蹤
                'stop_hit': 'SELL_ALL_MARKET',  # 停損就全出
                'time_stop': f"{holding_period['max_days']} days",  # 時間停損
                'signal_reversal': 'SELL_ALL'  # 訊號反轉就出場
            }
        
        # ============================================
        # D. 做空計劃 (SHORT) - 鏡像邏輯
        # ============================================
        elif action == 'SELL':
            
            entries = {
                'aggressive': price,
                'conservative': None,
                'ideal': None,
                'limit_order': None
            }
            
            if bb_middle > 0 and price < bb_middle:
                entries['conservative'] = round(bb_middle, 2)
            elif resistance > 0:
                entries['conservative'] = round(resistance * 0.995, 2)
            else:
                entries['conservative'] = round(price * 1.015, 2)
            
            if resistance > 0 and bb_upper > 0:
                entries['ideal'] = round(min(resistance, bb_upper), 2)
            elif resistance > 0:
                entries['ideal'] = round(resistance, 2)
            elif bb_upper > 0:
                entries['ideal'] = round(bb_upper, 2)
            else:
                entries['ideal'] = round(price + atr * 0.5, 2)
            
            entries['limit_order'] = entries['conservative']
            
            stops = {
                'hard_stop': round(price + atr * stop_atr_multiplier, 2),
                'soft_stop': None,
                'trailing_stop': round(price * 0.90, 2),
                'mental_stop': round(price * 1.05, 2)
            }
            
            if resistance > 0:
                resistance_stop = round(resistance * 1.005, 2)
                stops['hard_stop'] = min(stops['hard_stop'], resistance_stop)
            
            stops['soft_stop'] = round(stops['hard_stop'] * 1.01, 2)
            
            targets = {
                'T1': round(price - atr * target_atr_multipliers[0], 2),
                'T2': round(price - atr * target_atr_multipliers[1], 2),
                'T3': round(price - atr * target_atr_multipliers[2], 2),
                'moon': None
            }
            
            if support > 0 and support > targets['T1']:
                targets['T1'] = round(support * 1.005, 2)
            
            if bb_lower > 0:
                targets['moon'] = round(bb_lower, 2)
            else:
                targets['moon'] = round(price * 0.80, 2)
            
            risk = stops['hard_stop'] - price
            reward_T1 = price - targets['T1']
            reward_T2 = price - targets['T2']
            reward_T3 = price - targets['T3']
            
            rr_ratios = {
                'T1': round(reward_T1 / risk, 2) if risk > 0 else 0,
                'T2': round(reward_T2 / risk, 2) if risk > 0 else 0,
                'T3': round(reward_T3 / risk, 2) if risk > 0 else 0,
            }
            
            # Use actual backtest data if available (same as BUY)
            kelly_source = "強度估算 (無回測)"
            if backtest_stats and backtest_stats.get('win_rate') and backtest_stats.get('avg_win') and backtest_stats.get('avg_loss'):
                actual_win_rate = backtest_stats['win_rate'] / 100
                avg_win = backtest_stats['avg_win']
                avg_loss = abs(backtest_stats['avg_loss'])

                if avg_loss > 0:
                    b = avg_win / avg_loss
                    kelly_fraction = (actual_win_rate * b - (1 - actual_win_rate)) / b
                else:
                    kelly_fraction = 0.10

                kelly_source = f"回測勝率 {backtest_stats['win_rate']:.1f}%"
            else:
                win_rate_map = {5: 0.60, 4: 0.55, 3: 0.50, 2: 0.45, 1: 0.40}
                estimated_win_rate = win_rate_map.get(strength, 0.48)

                if rr_ratios['T2'] > 0:
                    kelly_fraction = (estimated_win_rate * rr_ratios['T2'] - (1 - estimated_win_rate)) / rr_ratios['T2']
                else:
                    kelly_fraction = 0

            # LOW-RISK BTC: Half-Kelly with 15% hard cap
            kelly_fraction = max(0, min(kelly_fraction * 0.5, 0.15))

            position_sizing = {
                'kelly_fraction': round(kelly_fraction, 3),
                'conservative': round(kelly_fraction * 0.5, 3),
                'aggressive': round(kelly_fraction * 1.5, 3),
                'max_risk_percent': 1.5,
                'recommended': None,
                'kelly_source': kelly_source
            }
            
            if strength >= 4:
                position_sizing['recommended'] = position_sizing['aggressive']
            elif strength == 3:
                position_sizing['recommended'] = position_sizing['kelly_fraction']
            else:
                position_sizing['recommended'] = position_sizing['conservative']
            
            position_sizing['recommended'] = min(position_sizing['recommended'], 0.20)
            
            pyramiding = {
                'enabled': strength >= 4 and regime == 'trending_strong',
                'add_on_levels': [],
                'reduce_size_by': 0.5
            }
            
            if pyramiding['enabled']:
                pyramiding['add_on_levels'] = [
                    round(price * 0.95, 2),
                    round(price * 0.90, 2),
                    round(price * 0.85, 2)
                ]
            
            if atr > 0:
                days_to_T1 = abs(price - targets['T1']) / atr
                days_to_T2 = abs(price - targets['T2']) / atr
            else:
                days_to_T1 = 5
                days_to_T2 = 10
            
            holding_period = {
                'min_days': max(1, int(days_to_T1 * 0.5)),
                'expected_days': int(days_to_T1),
                'max_days': int(days_to_T2),
                'regime_factor': regime
            }
            
            exit_strategy = {
                'T1_action': 'COVER_33%',
                'T2_action': 'COVER_33%',
                'T3_action': 'COVER_REMAINING_OR_TRAIL',
                'stop_hit': 'COVER_ALL_MARKET',
                'time_stop': f"{holding_period['max_days']} days",
                'signal_reversal': 'COVER_ALL'
            }
        
        # ============================================
        # E. 風險警告旗標
        # ============================================
        risk_warnings = []
        
        # 風報比太低
        if rr_ratios.get('T1', 0) < 1.5:
            risk_warnings.append('⚠️ RR比<1.5，風險報酬不佳')
        
        # 波動率過高
        if volatility == 'high':
            risk_warnings.append('⚠️ 高波動市場，加大停損空間')
        
        # 盤整市況
        if regime == 'ranging':
            risk_warnings.append('⚠️ 盤整市場，縮小目標')
        
        # 低量
        if df is not None and len(df) >= 20:
            volume_ma = df['volume'].rolling(20).mean().iloc[-1]
            if df.iloc[-1]['volume'] < volume_ma * 0.5:
                risk_warnings.append('⚠️ 成交量低迷，流動性風險')
        
        # RSI極端
        if rsi > 75 and action == 'BUY':
            risk_warnings.append('⚠️ RSI>75超買，注意回調')
        elif rsi < 25 and action == 'SELL':
            risk_warnings.append('⚠️ RSI<25超賣，注意反彈')
        
        # ============================================
        # F. 完整交易計劃返回
        # ============================================
        return {
            # 市場分析
            'market_regime': regime,
            'volatility': volatility,
            'atr_percent': round(atr_percent, 2),
            
            # 入場計劃
            'entries': entries,
            'entry_recommendation': '激進用市價，保守掛限價單' if strength >= 4 else '建議掛保守價等待',
            
            # 停損計劃
            'stops': stops,
            'stop_recommendation': f"硬停損 {stops['hard_stop']}，絕不能破",
            
            # 獲利目標
            'targets': targets,
            'target_recommendation': f"分批出場：T1賣1/3, T2賣1/3, T3視情況",
            
            # 風險報酬
            'risk_reward_ratios': rr_ratios,
            'min_acceptable_rr': 1.5,
            'actual_best_rr': rr_ratios.get('T2', 0),
            
            # 倉位管理
            'position_sizing': position_sizing,
            'position_recommendation': f"{position_sizing['recommended']*100:.1f}% 總資金",
            
            # 加碼策略
            'pyramiding': pyramiding,
            
            # 時間管理
            'holding_period': holding_period,
            'time_stop_enabled': True,
            
            # 出場策略
            'exit_strategy': exit_strategy,
            
            # 風險提示
            'risk_warnings': risk_warnings,
            
            # 勝率估算
            'estimated_win_rate': round(estimated_win_rate * 100, 1),
            
            # 預期報酬（期望值）
            'expected_return': round(
                estimated_win_rate * (reward_T2 / price * 100) - 
                (1 - estimated_win_rate) * (risk / price * 100), 
                2
            ) if price > 0 and risk > 0 else 0,
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
