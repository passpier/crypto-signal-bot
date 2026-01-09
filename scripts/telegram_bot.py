"""Telegram notification module for sending trading signals."""
import asyncio
import logging
import json
from typing import Dict, Optional
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.error import TelegramError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logging.warning("python-telegram-bot not available. Telegram notifications disabled.")

from scripts.utils import load_config

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Handles Telegram notifications for trading signals."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize Telegram notifier.
        
        Args:
            config_path: Path to config file. Defaults to config/config.yaml
        """
        if not TELEGRAM_AVAILABLE:
            raise ImportError("python-telegram-bot is required for Telegram notifications")
        
        config = load_config(config_path)
        
        telegram_token = config['api_keys']['telegram_token']
        telegram_chat_id = config['api_keys']['telegram_chat_id']
        
        if not telegram_token or telegram_token == "YOUR_TELEGRAM_TOKEN":
            raise ValueError("Telegram token not configured")
        if not telegram_chat_id or telegram_chat_id == "YOUR_CHAT_ID":
            raise ValueError("Telegram chat ID not configured")
        
        self.bot = Bot(token=telegram_token)
        self.chat_id = str(telegram_chat_id)
        logger.info("Telegram notifier initialized")
    
    def _parse_ai_advice_json(self, ai_advice_text: str) -> Optional[Dict]:
        """
        Parse AI advice JSON string.
        
        Args:
            ai_advice_text: JSON string from AI analysis
            
        Returns:
            Parsed dictionary or None if parsing fails
        """
        if not ai_advice_text or not ai_advice_text.strip():
            return None
        
        try:
            # Try to parse JSON
            parsed = json.loads(ai_advice_text)
            return parsed
        except json.JSONDecodeError:
            # If not JSON, return None
            return None
        except Exception as e:
            logger.warning(f"Failed to parse AI advice JSON: {e}")
            return None
    
    async def send_signal(
        self, 
        signal: Dict, 
        sentiment: Optional[Dict] = None,
    ) -> bool:
        """
        Send simplified trading signal to Telegram.
        
        Args:
            signal: Signal dictionary with action, price, indicators, etc.
            sentiment: Sentiment analysis results from sentiment_analyzer
            
        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            # Get AI advice from sentiment
            ai_advice_text = sentiment.get('ai_advice_text', '') if sentiment else ''
            
            # Try to parse JSON
            ai_data = self._parse_ai_advice_json(ai_advice_text)
            
            # Get data from signal and sentiment
            current_price = signal.get('price', 0)
            rsi = signal['indicators'].get('rsi') if signal.get('indicators') else None
            macd = signal['indicators'].get('macd') if signal.get('indicators') else None
            volume_change = signal['indicators'].get('volume_change', 0) if signal.get('indicators') else 0
            fear_greed_value = sentiment.get('fear_greed_value') if sentiment else None
            fear_greed_class = sentiment.get('fear_greed_class', 'Neutral') if sentiment else 'Neutral'
            
            # Map action to Chinese
            action_map = {
                'BUY': '買入',
                'SELL': '賣出',
                'HOLD': '觀望'
            }
            
            # Use AI data if available, otherwise fallback to signal
            if ai_data:
                signal_action = ai_data.get('signal', signal.get('action', 'HOLD'))
                signal_strength = ai_data.get('strength', signal.get('strength', 3))
                entry_range = ai_data.get('entry_range', {})
                target_price = ai_data.get('target_price', [])
                stop_loss = ai_data.get('stop_loss_price', {})
                risk_reward = ai_data.get('risk_reward_ratio', 0)
                risk_management = ai_data.get('risk_management', '')
                main_risk = ai_data.get('main_risk', '')
                key_factors = ai_data.get('key_factors', [])
            else:
                # Fallback to signal data or empty
                signal_action = signal.get('action', 'HOLD')
                signal_strength = signal.get('strength', 3)
                entry_range = {}
                target_price = []
                stop_loss = {}
                risk_reward = 0
                risk_management = ''
                main_risk = ''
                key_factors = []
            
            action_text = action_map.get(signal_action, '觀望')
            
            # Build message
            message = f"🔔 BTC {action_text}訊號 ({signal_strength}/5)\n\n"
            
            # Entry range
            if entry_range:
                entry_low = entry_range.get('low', 0)
                entry_high = entry_range.get('high', 0)
                if entry_low and entry_high:
                    message += f"入場: ${entry_low:,.0f}-${entry_high:,.0f}\n"
            
            # Current price
            if current_price > 0:
                message += f"現價: ${current_price:,.0f}\n"
            
            message += "━━━━━━━━━━━━━━━━\n"
            
            # Target price
            if target_price and len(target_price) > 0:
                # Use first target price
                first_target = target_price[0]
                target_price_value = first_target.get('price', 0)
                if target_price_value > 0 and current_price > 0:
                    target_pct = ((target_price_value / current_price) - 1) * 100
                    message += f"目標: ${target_price_value:,.0f} (+{target_pct:.1f}%)\n"
            
            # Stop loss
            if stop_loss:
                stop_loss_price_value = stop_loss.get('price', 0)
                stop_loss_pct = stop_loss.get('percentage', 0)
                if stop_loss_price_value > 0:
                    message += f"停損: ${stop_loss_price_value:,.0f}"
                    if stop_loss_pct > 0:
                        message += f" (-{stop_loss_pct:.1f}%)"
                    message += "\n"
            
            # Risk-reward ratio
            if risk_reward > 0:
                message += f"風報比: 1:{risk_reward:.1f}\n"
            
            message += "━━━━━━━━━━━━━━━━\n"
            
            # Indicators
            indicator_parts = []
            if rsi is not None:
                indicator_parts.append(f"RSI {rsi:.0f}")
            
            if macd is not None:
                macd_text = "多頭" if macd > 0 else "空頭"
                indicator_parts.append(f"MACD {macd_text}")
            
            if indicator_parts:
                message += " | ".join(indicator_parts) + "\n"
            
            # Fear & Greed
            if fear_greed_value is not None:
                message += f"恐懼指數: {fear_greed_value}/100 ({fear_greed_class})\n"
            
            # Volume change
            if volume_change != 0:
                message += f"成交量 {volume_change:+.0f}%\n"
            
            # Risk management
            if risk_management:
                message += f"\n💡風險管理建議: {risk_management}\n"
            
            # Main risk
            if main_risk:
                message += f"⚠️主要風險: {main_risk}\n"
            
            # Key factors
            if key_factors:
                message += "關鍵因素:\n"
                # Show first 3 key factors
                for factor in key_factors[:3]:
                    message += f"   • {factor}\n"
            
            # If no AI data, show raw text
            if not ai_data and ai_advice_text:
                message += f"\n🤖AI分析結果:\n\n{ai_advice_text}"
            
            # Add interactive button
            keyboard = [
                [InlineKeyboardButton(
                    "📊 查看圖表", 
                    url=f"https://www.tradingview.com/chart/?symbol=BTCUSDT"
                )],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                reply_markup=reply_markup
            )
            
            logger.info(f"Sent signal to Telegram: {action_text} ({signal_strength}/5)")
            return True
            
        except TelegramError as e:
            logger.error(f"Telegram error: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}", exc_info=True)
            return False
    
    async def send_backtest_results(self, results: Dict) -> bool:
        """
        Send backtest results to Telegram.
        
        Args:
            results: Dictionary with backtest statistics
            
        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            message = f"""
📊 **策略回測報告** (過去30天)

✅ 成功訊號: {results['wins']}次
❌ 失敗訊號: {results['losses']}次
📈 勝率: {results['win_rate']:.1f}%
💰 平均獲利: {results['avg_profit']:+.2f}%
📉 最大回撤: {results['max_drawdown']:.2f}%
"""
            if 'best_trade' in results:
                message += f"🏆 最佳交易: +{results['best_trade']:.2f}%\n"
            if 'total_trades' in results:
                message += f"📊 總交易次數: {results['total_trades']}\n"
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info("Sent backtest results to Telegram")
            return True
            
        except TelegramError as e:
            logger.error(f"Telegram error: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to send backtest results: {e}", exc_info=True)
            return False


# Test
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if not TELEGRAM_AVAILABLE:
        print("Error: python-telegram-bot is not installed", file=sys.stderr)
        sys.exit(1)
    
    try:
        notifier = TelegramNotifier()
        
        # Simulate test signal
        test_signal = {
            'action': 'BUY',
            'strength': 4,
            'price': 89642,
            'entry_range': (89500, 89800),
            'stop_loss': 87800,
            'take_profit': 92500,
            'risk_reward': 1.7,
            'reasons': ['RSI 28 超賣反彈', 'MACD黃金交叉'],
            'technical_summary': '技術面轉強',
            'indicators': {
                'rsi': 28,
                'macd': 0.05,
                'volume_change': 45,
                'price_change_24h': -2.71
            }
        }
        
        # Test sentiment
        test_sentiment = {
            'fear_greed_value': 29,
            'fear_greed_class': 'Fear',
            'sentiment_class': '恐懼',
            'consistency': '一致看多',
            'recommendation': '分批建倉'
        }
        
        # Test backtest stats
        test_backtest = {
            'win_rate': 78,
            'total_trades': 45
        }
        
        asyncio.run(notifier.send_signal(test_signal, test_sentiment, test_backtest))
        print("✅ Test signal sent successfully!")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)

