"""Backtesting module for trading strategy evaluation."""
import pandas as pd
import logging
from typing import Dict
import numpy as np
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.signal_generator import SignalGenerator
from scripts.data_fetcher import CryptoDataFetcher

logger = logging.getLogger(__name__)


class SimpleBacktest:
    """Simple backtesting engine for trading signals."""
    
    def __init__(self):
        """Initialize backtest engine."""
        self.generator = SignalGenerator()
        self.fetcher = CryptoDataFetcher()
    
    def run_backtest(self, days: int = 30) -> Dict:
        """
        Run backtest on historical data.
        
        Args:
            days: Number of days of historical data to use
            
        Returns:
            Dictionary with backtest statistics
        """
        # Determine interval from config
        interval = self.generator.config['trading'].get('interval', '1h')
        
        # Adjust days based on interval to avoid API limits (1000 candles)
        if interval == '15m':
            days = min(days, 5) # Max 5 days for 15m
        
        logger.info(f"Starting backtest with {days} days of data ({interval} interval)")
        
        try:
            # Fetch and prepare data
            df = self.fetcher.fetch_historical_data(days=days, interval=interval)
            df = self.generator.calculate_indicators(df)
            
            if len(df) < 200:
                logger.warning(f"Insufficient data ({len(df)} rows). Need at least 200 for MA200 calculation.")
                return {
                    'wins': 0,
                    'losses': 0,
                    'win_rate': 0,
                    'avg_profit': 0,
                    'avg_win': 0,
                    'avg_loss': 0,
                    'max_drawdown': 0,
                    'best_trade': 0,
                    'worst_trade': 0,
                    'total_trades': 0,
                    'total_return': 0,
                    'equity_curve': [],
                    'error': 'Insufficient data'
                }
            
            results = []
            equity_curve = []
            initial_equity = 10000  # Starting capital
            
            # Simulate trading day by day
            # Start from index 50 to ensure indicators are calculated
            for i in range(50, len(df) - 24):  # Leave 24 hours for future price check
                try:
                    window_df = df.iloc[:i+1].copy()
                    signal = self.generator.calculate_signal_strength(window_df)
                    
                    if signal['action'] in ['BUY', 'SELL']:
                        # Simulate trade
                        entry_price = signal.get('price', df.iloc[i]['close'])
                        trade_plan = signal.get('trade_plan')

                        if not trade_plan:
                            continue

                        stops = trade_plan.get('stops', {})
                        targets = trade_plan.get('targets', {})
                        stop_loss = stops.get('hard_stop', 0)
                        take_profit = targets.get('T2', 0)
                        
                        # Check future prices (next 24 hours)
                        future_prices = df.iloc[i+1:i+25]['close']
                        
                        if len(future_prices) == 0:
                            continue
                        
                        if signal['action'] == 'BUY':
                            # Check if stop loss or take profit is hit
                            hit_stop_loss = (future_prices < stop_loss).any()
                            hit_take_profit = (future_prices > take_profit).any()
                            
                            if hit_stop_loss:
                                # Find when stop loss was hit
                                stop_loss_idx = (future_prices < stop_loss).idxmax()
                                exit_price = stop_loss
                                profit_pct = (stop_loss / entry_price - 1) * 100
                            elif hit_take_profit:
                                # Find when take profit was hit
                                take_profit_idx = (future_prices > take_profit).idxmax()
                                exit_price = take_profit
                                profit_pct = (take_profit / entry_price - 1) * 100
                            else:
                                # Exit at last available price
                                exit_price = future_prices.iloc[-1]
                                profit_pct = (exit_price / entry_price - 1) * 100
                        else:  # SELL (short)
                            # Reverse logic for short positions
                            hit_stop_loss = (future_prices > stop_loss).any()
                            hit_take_profit = (future_prices < take_profit).any()
                            
                            if hit_stop_loss:
                                exit_price = stop_loss
                                profit_pct = (entry_price / stop_loss - 1) * 100
                            elif hit_take_profit:
                                exit_price = take_profit
                                profit_pct = (entry_price / take_profit - 1) * 100
                            else:
                                exit_price = future_prices.iloc[-1]
                                profit_pct = (entry_price / exit_price - 1) * 100
                        
                        results.append({
                            'date': df.iloc[i]['timestamp'],
                            'action': signal['action'],
                            'entry': entry_price,
                            'exit': exit_price,
                            'profit_pct': profit_pct,
                            'win': profit_pct > 0
                        })
                        
                except Exception as e:
                    logger.warning(f"Error processing signal at index {i}: {e}")
                    continue
            
            # Calculate statistics
            if not results:
                logger.warning("No trades generated during backtest")
                return {
                    'wins': 0,
                    'losses': 0,
                    'win_rate': 0,
                    'avg_profit': 0,
                    'avg_win': 0,
                    'avg_loss': 0,
                    'max_drawdown': 0,
                    'best_trade': 0,
                    'worst_trade': 0,
                    'total_trades': 0,
                    'total_return': 0,
                    'equity_curve': []
                }
            
            df_results = pd.DataFrame(results)
            wins = df_results['win'].sum()
            losses = (~df_results['win']).sum()
            total = len(df_results)

            # Separate winning and losing trades
            winning_trades = df_results[df_results['win']]
            losing_trades = df_results[~df_results['win']]

            # Calculate equity curve
            cumulative_profit = (1 + df_results['profit_pct'] / 100).cumprod()
            equity_curve = initial_equity * cumulative_profit

            # Calculate maximum drawdown
            peak = equity_curve.expanding().max()
            drawdown = (equity_curve - peak) / peak * 100
            max_drawdown = drawdown.min()

            stats = {
                'wins': int(wins),
                'losses': int(losses),
                'win_rate': (wins / total * 100) if total > 0 else 0,
                'avg_profit': float(df_results['profit_pct'].mean()),
                'avg_win': float(winning_trades['profit_pct'].mean()) if len(winning_trades) > 0 else 0,
                'avg_loss': float(losing_trades['profit_pct'].mean()) if len(losing_trades) > 0 else 0,
                'max_drawdown': float(max_drawdown),
                'best_trade': float(df_results['profit_pct'].max()),
                'worst_trade': float(df_results['profit_pct'].min()),
                'total_trades': int(total),
                'total_return': float((equity_curve.iloc[-1] / initial_equity - 1) * 100) if len(equity_curve) > 0 else 0,
                'equity_curve': equity_curve.tolist()  # Store equity curve for sparkline display
            }
            
            logger.info(f"Backtest completed: {stats['win_rate']:.1f}% win rate, {stats['total_trades']} trades")
            return stats
            
        except Exception as e:
            logger.error(f"Backtest failed: {e}", exc_info=True)
            return {
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'avg_profit': 0,
                'max_drawdown': 0,
                'best_trade': 0,
                'total_trades': 0,
                'error': str(e)
            }


# Test
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    try:
        backtest = SimpleBacktest()
        results = backtest.run_backtest(days=30)
        
        print("=== 回測結果 ===")
        print(f"總交易次數: {results['total_trades']}")
        print(f"勝率: {results['win_rate']:.1f}%")
        print(f"平均獲利: {results['avg_profit']:+.2f}%")
        print(f"最佳交易: +{results['best_trade']:.2f}%")
        if 'worst_trade' in results:
            print(f"最差交易: {results['worst_trade']:.2f}%")
        print(f"最大回撤: {results['max_drawdown']:.2f}%")
        if 'total_return' in results:
            print(f"總報酬率: {results['total_return']:+.2f}%")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)

