"""Telegram notification module for sending trading signals."""
import asyncio
import logging
import re
from typing import Dict, Optional
from pathlib import Path
import sys

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
        """Initialize Telegram notifier."""
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
    
    def _parse_text_signal(self, ai_text: str) -> Dict:
        """
        Parse structured text with better tolerance for formatting variations.
        """
        if not ai_text or not ai_text.strip():
            return {}
        
        try:
            data = {}
            
            # Parse signal
            signal_match = re.search(r'訊號[:：]\s*(BUY|SELL|HOLD|買入|賣出|觀望)', ai_text, re.IGNORECASE)
            if signal_match:
                signal_map = {'買入': 'BUY', '賣出': 'SELL', '觀望': 'HOLD'}
                raw_signal = signal_match.group(1)
                data['signal'] = signal_map.get(raw_signal, raw_signal.upper())
            
            # Parse strength
            strength_match = re.search(r'強度[:：]\s*(\d)', ai_text)
            if strength_match:
                data['strength'] = int(strength_match.group(1))
            
            # === FIX: Parse entry range (allow $ and commas) ===
            entry_match = re.search(r'入場[:：]\s*\$?([\d,]+)\s*[-~]\s*\$?([\d,]+)', ai_text)
            if entry_match:
                data['entry_range'] = {
                    'low': float(entry_match.group(1).replace(',', '')),
                    'high': float(entry_match.group(2).replace(',', ''))
                }
            
            # === FIX: Parse target (allow $ and commas) ===
            target_match = re.search(r'目標[:：]\s*\$?([\d,]+)\s*\(([+-]?[\d.]+)%\)', ai_text)
            if target_match:
                price = float(target_match.group(1).replace(',', ''))
                pct = abs(float(target_match.group(2)))  # Remove sign for display
                data['target_price'] = [{
                    'price': price,
                    'percentage': pct
                }]
            
            # === FIX: Parse stop loss (allow $ and commas) ===
            stop_match = re.search(r'停損[:：]\s*\$?([\d,]+)\s*\(([+-]?[\d.]+)%\)', ai_text)
            if stop_match:
                price = float(stop_match.group(1).replace(',', ''))
                pct = abs(float(stop_match.group(2)))
                data['stop_loss_price'] = {
                    'price': price,
                    'percentage': pct
                }
            
            # Parse risk-reward (allow colon or Chinese colon)
            rr_match = re.search(r'風報比[:：]\s*1[:：]([\d.]+)', ai_text)
            if rr_match:
                data['risk_reward_ratio'] = float(rr_match.group(1))
            
            # === FIX: Parse analysis (handle escaped \n) ===
            # Replace escaped newlines with actual newlines first
            ai_text_clean = ai_text.replace('\\n', '\n')
            
            reason_match = re.search(r'理由[:：]\s*(.+?)(?=\n?倉位|\n?風險|$)', ai_text_clean, re.DOTALL)
            if reason_match:
                reasons_text = reason_match.group(1).strip()
                data['key_factors'] = [reasons_text]
            
            # Parse risk management
            position_match = re.search(r'倉位[:：]\s*(.+?)(?=\n?風險|$)', ai_text_clean, re.DOTALL)
            if position_match:
                data['risk_management'] = position_match.group(1).strip()
            
            # Parse main risk
            risk_match = re.search(r'風險[:：]\s*(.+?)$', ai_text_clean, re.DOTALL)
            if risk_match:
                data['main_risk'] = risk_match.group(1).strip()
            
            logger.info(f"Parsed {len(data)} fields from AI text")
            return data
            
        except Exception as e:
            logger.warning(f"Failed to parse AI text: {e}")
            return {}
    
    async def send_signal(
        self, 
        signal: Dict, 
        sentiment: Optional[Dict] = None,
    ) -> bool:
        """
        Send formatted trading signal to Telegram.
        
        Args:
            signal: Signal dictionary with action, price, indicators
            sentiment: Sentiment analysis with ai_advice_text
            
        Returns:
            True if sent successfully
        """
        try:
            # Get AI advice and parse
            ai_advice_text = sentiment.get('ai_advice_text', '') if sentiment else ''
            ai_data = self._parse_text_signal(ai_advice_text)
            
            # Get basic data
            current_price = signal.get('price', 0)
            rsi = signal['indicators'].get('rsi') if signal.get('indicators') else None
            macd = signal['indicators'].get('macd') if signal.get('indicators') else None
            volume_change = signal['indicators'].get('volume_change', 0) if signal.get('indicators') else 0
            fear_greed_value = sentiment.get('fear_greed_value') if sentiment else None
            fear_greed_class = sentiment.get('fear_greed_class', 'Neutral') if sentiment else 'Neutral'
            
            # Get institutional data (if available)
            inst_summary = sentiment.get('institutional_summary', {}) if sentiment else {}
            etf_net = inst_summary.get('etf_net_m') if inst_summary else None
            lsr_ratio = inst_summary.get('lsr_ratio') if inst_summary else None
            
            # Action mapping
            action_map = {'BUY': '買入', 'SELL': '賣出', 'HOLD': '觀望'}
            
            # Use AI data if available, else fallback
            signal_action = ai_data.get('signal', signal.get('action', 'HOLD'))
            signal_strength = ai_data.get('strength', signal.get('strength', 3))
            entry_range = ai_data.get('entry_range', {})
            target_price = ai_data.get('target_price', [])
            stop_loss = ai_data.get('stop_loss_price', {})
            risk_reward = ai_data.get('risk_reward_ratio', 0)
            risk_management = ai_data.get('risk_management', '')
            main_risk = ai_data.get('main_risk', '')
            key_factors = ai_data.get('key_factors', [])
            
            action_text = action_map.get(signal_action, '觀望')
            
            # === Build formatted message ===
            
            # Header with emoji
            action_emoji = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡'}
            emoji = action_emoji.get(signal_action, '🟡')
            
            message = f"{emoji} **BTC {action_text}訊號** ({signal_strength}/5)\n\n"
            
            # Price section
            message += "**價格資訊**\n"
            if current_price > 0:
                message += f"現價: ${current_price:,.0f}\n"
            
            if entry_range:
                entry_low = entry_range.get('low', 0)
                entry_high = entry_range.get('high', 0)
                if entry_low and entry_high:
                    message += f"入場: ${entry_low:,.0f}-${entry_high:,.0f}\n"
            
            if target_price and len(target_price) > 0:
                first_target = target_price[0]
                target_price_value = first_target.get('price', 0)
                target_pct = first_target.get('percentage', 0)
                if target_price_value > 0:
                    if target_pct:
                        message += f"目標: ${target_price_value:,.0f} (+{target_pct:.1f}%)\n"
                    else:
                        message += f"目標: ${target_price_value:,.0f}\n"
            
            if stop_loss:
                stop_price = stop_loss.get('price', 0)
                stop_pct = stop_loss.get('percentage', 0)
                if stop_price > 0:
                    if stop_pct:
                        message += f"停損: ${stop_price:,.0f} (-{stop_pct:.1f}%)\n"
                    else:
                        message += f"停損: ${stop_price:,.0f}\n"
            
            if risk_reward > 0:
                message += f"風報比: 1:{risk_reward:.1f}\n"
            
            message += "━━━━━━━━━━━━━━━━\n"
            
            # Technical indicators
            message += "**技術指標**\n"
            indicator_parts = []
            if rsi is not None:
                indicator_parts.append(f"RSI {rsi:.0f}")
            if macd is not None:
                macd_text = "多頭" if macd > 0 else "空頭"
                indicator_parts.append(f"MACD {macd_text}")
            if indicator_parts:
                message += " | ".join(indicator_parts) + "\n"
            
            # Market sentiment
            if fear_greed_value is not None:
                message += f"恐懼指數: {fear_greed_value}/100 ({fear_greed_class})\n"
            
            if volume_change != 0:
                message += f"成交量: {volume_change:+.0f}%\n"
            
            # Institutional data (if available)
            if etf_net is not None or lsr_ratio is not None:
                message += "\n**機構數據**\n"
                if etf_net is not None:
                    message += f"ETF 淨流: ${etf_net:.0f}M\n"
                if lsr_ratio is not None:
                    message += f"多空比: {lsr_ratio:.2f}\n"
            
            message += "━━━━━━━━━━━━━━━━\n"
            
            # Analysis sections
            if key_factors:
                message += "💡 **分析理由**\n"
                for i, factor in enumerate(key_factors[:3], 1):
                    # Clean up factor text
                    factor_clean = factor.strip()
                    message += f"{factor_clean}\n"
                message += "\n"
            
            if risk_management:
                message += f"📋 **倉位管理**\n{risk_management}\n\n"
            
            if main_risk:
                message += f"⚠️ **風險提示**\n{main_risk}\n\n"
            
            # If parsing failed, show raw AI text
            if not ai_data and ai_advice_text:
                message += "━━━━━━━━━━━━━━━━\n\n"
                message += "🤖 **AI 完整分析**\n\n"
                message += ai_advice_text
            
            # Add TradingView button
            keyboard = [
                [InlineKeyboardButton(
                    "📊 查看圖表", 
                    url="https://www.tradingview.com/chart/?symbol=BTCUSDT"
                )],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send with Markdown formatting
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
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
        """Send backtest results to Telegram."""
        try:
            message = f"""
**策略回測報告** (過去30天)

成功訊號: {results['wins']}次
失敗訊號: {results['losses']}次
勝率: {results['win_rate']:.1f}%
平均獲利: {results['avg_profit']:+.2f}%
最大回撤: {results['max_drawdown']:.2f}%
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
        
        # Test with structured text AI output
        test_sentiment = {
            'ai_advice_text': """訊號: HOLD
強度: 3
入場: 77500-78000
目標: 80500 (+3.2%)
停損: 76800 (-2.1%)
風報比: 1:1.5
理由: 極度恐懼但ETF流出，RSI中性MACD轉多，技術面未破位但機構觀望
倉位: 20%輕倉試探，分3批進場，每批間隔1H
風險: 跌破76500確認空頭，目標74000""",
            'fear_greed_value': 17,
            'fear_greed_class': 'Extreme Fear',
            'institutional_summary': {
                'etf_net_m': -492.9,
                'lsr_ratio': 2.67
            }
        }
        
        test_signal = {
            'action': 'HOLD',
            'strength': 3,
            'price': 78478,
            'indicators': {
                'rsi': 55,
                'macd': 160,
                'volume_change': -64.9
            }
        }
        
        asyncio.run(notifier.send_signal(test_signal, test_sentiment))
        print("✅ Test signal sent successfully!")
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
