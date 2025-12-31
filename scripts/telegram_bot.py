"""Telegram notification module for sending trading signals."""
import asyncio
import logging
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
    
    async def send_signal(
        self, 
        signal: Dict, 
        sentiment: Optional[Dict] = None,
        backtest_stats: Optional[Dict] = None
    ) -> bool:
        """
        Send simplified trading signal to Telegram.
        
        Args:
            signal: Signal dictionary with action, price, indicators, etc.
            sentiment: Sentiment analysis results from sentiment_analyzer
            backtest_stats: Optional backtest statistics (win_rate, etc.)
            
        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            # Map action to Chinese
            action_map = {
                'BUY': '買入',
                'SELL': '賣出',
                'HOLD': '觀望',
                'STRONG_BUY': '強力買入',
                'STRONG_SELL': '強力賣出'
            }
            
            # Get combined recommendation
            combined = self._get_combined_recommendation(signal, sentiment)
            action_text = action_map.get(combined['action'], '觀望')
            
            # Get price info
            price = signal['price']
            price_change_24h = signal['indicators'].get('price_change_24h', 0)
            take_profit_pct = ((signal['take_profit'] / price) - 1) * 100
            stop_loss_pct = ((signal['stop_loss'] / price) - 1) * 100
            
            # Get indicators
            rsi = signal['indicators'].get('rsi')
            volume_change = signal['indicators'].get('volume_change', 0)
            
            # Get sentiment info
            fear_greed = sentiment.get('fear_greed_value', 50) if sentiment else None
            fear_greed_class = sentiment.get('sentiment_class', '') if sentiment else ''
            
            # Build signal reasons
            reasons = []
            
            # RSI reason
            if rsi is not None:
                if rsi < 30:
                    reasons.append(f"RSI {rsi:.0f} 超賣反彈")
                elif rsi > 70:
                    reasons.append(f"RSI {rsi:.0f} 超買回調")
                else:
                    reasons.append(f"RSI {rsi:.0f}")
            
            # Fear & Greed reason
            if fear_greed is not None:
                if fear_greed <= 25:
                    reasons.append(f"恐懼指數 {fear_greed} 極度恐懼")
                elif fear_greed <= 40:
                    reasons.append(f"恐懼指數 {fear_greed} 恐懼")
                elif fear_greed >= 75:
                    reasons.append(f"恐懼指數 {fear_greed} 極度貪婪")
                elif fear_greed >= 60:
                    reasons.append(f"恐懼指數 {fear_greed} 貪婪")
                else:
                    reasons.append(f"恐懼指數 {fear_greed} 中性")
            
            # Volume reason
            if volume_change != 0:
                reasons.append(f"成交量 {volume_change:+.0f}%")
            
            # Get AI advice from sentiment (Gemini output or template fallback)
            ai_generated = sentiment.get('ai_generated', False) if sentiment else False
            ai_advice_text = sentiment.get('ai_advice_text', '') if sentiment else ''
            
            # If no AI advice available, use rule-based fallback
            if not ai_advice_text:
                ai_advice_text = self._generate_ai_advice(combined['action'], signal['strength'], fear_greed)
                ai_generated = False
            
            # Title changes based on whether Gemini was used
            advice_title = "AI風險管理建議" if ai_generated else "風險管理建議"
            
            # Build simplified message
            message = f"""🔔 BTC {action_text}訊號 ({signal['strength']}/5)

入場: ${signal['entry_range'][0]:,.0f}-${signal['entry_range'][1]:,.0f}
現價: ${price:,.0f} ({price_change_24h:+.2f}%)
━━━━━━━━━━━━━━━━
目標: ${signal['take_profit']:,.0f} (+{take_profit_pct:.1f}%)
停損: ${signal['stop_loss']:,.0f} ({stop_loss_pct:.1f}%)
風報比: 1:{signal['risk_reward']:.1f}
━━━━━━━━━━━━━━━━
訊號依據:
"""
            # Add reasons
            for reason in reasons:
                message += f"• {reason}\n"
            
            # Add AI/Template advice with appropriate title
            message += f"""
{advice_title}:
{ai_advice_text}"""
            
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
            
            logger.info(f"Sent signal to Telegram: {action_text} ({signal['strength']}/5)")
            return True
            
        except TelegramError as e:
            logger.error(f"Telegram error: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}", exc_info=True)
            return False
    
    def _generate_ai_advice(self, action: str, strength: int, fear_greed: Optional[int]) -> str:
        """
        Generate AI risk management advice with conditional language.
        
        Args:
            action: Combined action (BUY/SELL/HOLD/STRONG_BUY/STRONG_SELL)
            strength: Signal strength (1-5)
            fear_greed: Fear & Greed index value
            
        Returns:
            Risk management advice string
        """
        if action == 'STRONG_BUY':
            if strength >= 4:
                return "若決定進場，建議分 2-3 批，首批不超過 40% 倉位，並嚴設停損"
            else:
                return "若考慮進場，可分批建倉，首批建議 30% 倉位，觀察後續走勢"
        elif action == 'BUY':
            if fear_greed and fear_greed < 40:
                return "市場情緒偏低，若進場可分 2 批，首批 30%，注意控制風險"
            else:
                return "若嘗試進場，建議輕倉 20-30%，設好停損再行動"
        elif action == 'STRONG_SELL':
            return "若持有部位，可考慮減倉 50-70%，保留部分觀察後續"
        elif action == 'SELL':
            if fear_greed and fear_greed > 60:
                return "市場情緒偏高，若有獲利可考慮減倉 30-50%，落袋為安"
            else:
                return "若持有部位，可考慮適度減倉 20-30%，等待更好時機"
        else:  # HOLD
            return "目前訊號不明確，建議暫時觀望，等待更清晰的進場點"
    
    def _get_combined_recommendation(self, signal: Dict, sentiment: Optional[Dict]) -> Dict:
        """
        Combine technical signal with sentiment analysis for final recommendation.
        
        Combined Strategy Logic:
        - Technical and Sentiment agree: HIGH confidence
        - Technical strong, Sentiment neutral: MEDIUM confidence  
        - Technical and Sentiment disagree: LOW confidence, prefer HOLD
        """
        tech_action = signal['action']
        tech_strength = signal['strength']
        
        # Default if no sentiment
        if not sentiment:
            return {
                'action': tech_action,
                'confidence': min(tech_strength * 20, 100)
            }
        
        fear_greed = sentiment.get('fear_greed_value', 50)
        consistency = sentiment.get('consistency', '不明確')
        
        # Map sentiment to bullish/bearish
        sentiment_bullish = fear_greed > 60  # Greed = bullish
        sentiment_bearish = fear_greed < 40  # Fear = bearish (contrarian: good to buy)
        
        # Combined logic
        if tech_action == 'BUY':
            if sentiment_bearish:  # Extreme fear + Buy signal = Strong contrarian buy
                return {'action': 'STRONG_BUY', 'confidence': min(90, tech_strength * 18 + 20)}
            elif sentiment_bullish:  # Greed + Buy signal = Caution, may be top
                return {'action': 'BUY', 'confidence': min(70, tech_strength * 14)}
            else:  # Neutral sentiment
                return {'action': 'BUY', 'confidence': min(80, tech_strength * 16)}
        
        elif tech_action == 'SELL':
            if sentiment_bullish:  # Extreme greed + Sell signal = Strong contrarian sell
                return {'action': 'STRONG_SELL', 'confidence': min(90, tech_strength * 18 + 20)}
            elif sentiment_bearish:  # Fear + Sell signal = Caution, may be bottom
                return {'action': 'SELL', 'confidence': min(70, tech_strength * 14)}
            else:  # Neutral sentiment
                return {'action': 'SELL', 'confidence': min(80, tech_strength * 16)}
        
        else:  # HOLD
            # Check if sentiment gives us a directional hint
            if consistency == '一致看多':
                return {'action': 'BUY', 'confidence': 50}
            elif consistency == '一致看空':
                return {'action': 'SELL', 'confidence': 50}
            else:
                return {'action': 'HOLD', 'confidence': 40}
    
    
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

