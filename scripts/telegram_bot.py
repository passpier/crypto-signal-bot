"""Telegram notification module for sending trading signals."""
import asyncio
import logging
import re
import html
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
            
            # Parse confidence score
            confidence_match = re.search(r'信心評分[:：]\s*(\d+)(?:/10)?', ai_text)
            if confidence_match:
                confidence = int(confidence_match.group(1))
                data['confidence'] = max(1, min(10, confidence))
            
            # Parse entry range
            entry_match = re.search(r'入場[:：]\s*\$?([\d,]+)\s*[-~]\s*\$?([\d,]+)', ai_text)
            if entry_match:
                data['entry_range'] = {
                    'low': float(entry_match.group(1).replace(',', '')),
                    'high': float(entry_match.group(2).replace(',', ''))
                }
            
            # Parse target
            target_match = re.search(r'目標[:：]\s*\$?([\d,]+)\s*\(([+-]?[\d.]+)%\)', ai_text)
            if target_match:
                price = float(target_match.group(1).replace(',', ''))
                pct = abs(float(target_match.group(2)))
                data['target_price'] = [{
                    'price': price,
                    'percentage': pct
                }]
            
            # Parse stop loss
            stop_match = re.search(r'停損[:：]\s*\$?([\d,]+)\s*\(([+-]?[\d.]+)%\)', ai_text)
            if stop_match:
                price = float(stop_match.group(1).replace(',', ''))
                pct = abs(float(stop_match.group(2)))
                data['stop_loss_price'] = {
                    'price': price,
                    'percentage': pct
                }
            
            # Parse risk-reward
            rr_match = re.search(r'風報比[:：]\s*1[:：]([\d.]+)', ai_text)
            if rr_match:
                data['risk_reward_ratio'] = float(rr_match.group(1))
            
            # Parse holding period
            holding_match = re.search(r'(?:預期)?持有(?:期限)?[:：]\s*(\d+)[-~]?(\d+)?天', ai_text)
            if holding_match:
                min_days = int(holding_match.group(1))
                max_days = int(holding_match.group(2)) if holding_match.group(2) else min_days
                data['expected_holding_days'] = {'min': min_days, 'max': max_days}
            
            # Clean text
            ai_text_clean = ai_text.replace('\\n', '\n')
            
            # Define common sections
            next_sections = r'(?=\n?倉位|\n?風險|\n?設定類型分析|\n?類型|\n?模式特徵|\n?本次評估|$)'
            
            # Parse reason
            reason_match = re.search(r'理由[:：]\s*(.+?)' + next_sections, ai_text_clean, re.DOTALL)
            if reason_match:
                data['key_factors'] = [reason_match.group(1).strip()]
            
            # Parse risk management
            position_match = re.search(r'倉位[:：]\s*(.+?)' + next_sections, ai_text_clean, re.DOTALL)
            if position_match:
                data['risk_management'] = position_match.group(1).strip()
            
            # Parse main risk
            risk_match = re.search(r'風險[:：]\s*(.+?)' + next_sections, ai_text_clean, re.DOTALL)
            if risk_match:
                data['main_risk'] = risk_match.group(1).strip()
            
            # Parse pattern type
            pattern_type_match = re.search(r'\n類型[:：]\s*(.+?)(?=\n|模式特徵|$)', ai_text_clean)
            if pattern_type_match:
                data['pattern_type'] = pattern_type_match.group(1).strip()
            
            # Parse pattern characteristics
            characteristics = []
            char_section = re.search(
                r'模式特徵[:：]\s*(.+?)(?=本次評估|$)',
                ai_text_clean,
                re.DOTALL
            )
            if char_section:
                char_text = char_section.group(1).strip()
                char_items = re.findall(r'(?:[-•\d]+\.?)\s*(.+?)(?=\n|$)', char_text)
                characteristics = [c.strip() for c in char_items if c.strip()]
                
                # Fallback: handle inline numbered list like "1. ... 2. ... 3. ..."
                if not characteristics and char_text:
                    inline_parts = re.split(r'\s*(?:\d+)\.\s*', char_text)
                    inline_parts = [p.strip() for p in inline_parts if p.strip()]
                    if inline_parts:
                        characteristics = inline_parts
                    else:
                        characteristics = [char_text]
            data['pattern_characteristics'] = characteristics
            
            # Parse current assessment
            assessment = {}
            
            comparison_match = re.search(r'與典型案例相比[:：]\s*(.+?)(?=\n|特殊風險)', ai_text_clean)
            if comparison_match:
                assessment['vs_typical'] = comparison_match.group(1).strip()
            
            special_risk_match = re.search(r'特殊風險[:：]\s*(.+?)(?=\n|成功機率|$)', ai_text_clean)
            if special_risk_match:
                assessment['special_risk'] = special_risk_match.group(1).strip()
            
            if assessment:
                data['current_assessment'] = assessment
            
            logger.info(f"Parsed {len(data)} fields from AI text (confidence: {data.get('confidence', 'N/A')})")
            return data
            
        except Exception as e:
            logger.warning(f"Failed to parse AI text: {e}")
            return {}

    async def send_signal(
        self, 
        signal: Dict, 
        sentiment: Optional[Dict] = None,
    ) -> bool:
        """Send signal with expandable detailed analysis using HTML spoilers."""
        try:
            # Parse AI data
            ai_advice_text = sentiment.get('ai_advice_text', '') if sentiment else ''
            ai_data = self._parse_text_signal(ai_advice_text)
            
            # Extract key info
            signal_action = ai_data.get('signal', signal.get('action', 'HOLD'))
            signal_strength = ai_data.get('strength', signal.get('strength', 3))
            confidence_score = ai_data.get('confidence', 5)
            
            current_price = signal.get('price', 0)
            entry_range = ai_data.get('entry_range', {})
            target_price = ai_data.get('target_price', [])
            stop_loss = ai_data.get('stop_loss_price', {})
            risk_reward_ratio = ai_data.get('risk_reward_ratio', 0)
            
            pattern_type = ai_data.get('pattern_type', '')
            key_factors = ai_data.get('key_factors', [])
            risk_management = ai_data.get('risk_management', '')
            main_risk = ai_data.get('main_risk', '')
            
            # Action mapping
            action_map = {'BUY': '買入', 'SELL': '賣出', 'HOLD': '觀望'}
            action_emoji = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡'}
            
            action_text = action_map.get(signal_action, '觀望')
            emoji = action_emoji.get(signal_action, '🟡')
            confidence_emoji = self._get_confidence_emoji(confidence_score)
            
            # === BUILD SIMPLE MESSAGE (HTML FORMAT) ===
            message = f"{emoji} <b>BTC {action_text}訊號</b> (強度 {signal_strength}/5) {confidence_emoji}\n\n"
            
            # Price info (compact)
            message += f"現價: ${current_price:,.0f}\n"
            
            if entry_range:
                entry_low = entry_range.get('low', 0)
                entry_high = entry_range.get('high', 0)
                if entry_low and entry_high:
                    message += f"入場: ${entry_low:,.0f}-${entry_high:,.0f}\n"
            
            if target_price and len(target_price) > 0:
                target = target_price[0]
                target_price_value = target.get('price', 0)
                target_pct = target.get('percentage', 0)
                if target_price_value > 0:
                    message += f"目標: ${target_price_value:,.0f} (+{target_pct:.1f}%)\n"
            
            if stop_loss:
                stop_price = stop_loss.get('price', 0)
                stop_pct = stop_loss.get('percentage', 0)
                if stop_price > 0:
                    message += f"停損: ${stop_price:,.0f} (-{stop_pct:.1f}%)\n"
            
            if risk_reward_ratio:
                message += f"風報比: 1:{risk_reward_ratio:.1f}\n"
            
            message += "━━━━━━━━━━━━━━━━\n"
            
            # Pattern + Confidence (one line)
            if pattern_type:
                message += f"📊 設定: {html.escape(pattern_type)}\n"
            message += f"✨ 信心: {confidence_score}/10\n\n"
            
            # Why? (1-2 sentences max)
            if key_factors:
                reason = html.escape(key_factors[0])
                message += f"💡 <b>為什麼{action_text}?</b>\n{reason}\n\n"
            
            # How? (Position sizing in 1 line)
            if risk_management:
                position_brief = html.escape(risk_management.split('\n')[0])  # First line, escape
                message += f"📋 <b>怎麼做?</b>\n{position_brief}\n\n"
            
            # When to exit? (Most important!)
            if main_risk:
                risk_brief = html.escape(main_risk.split('\n')[0])
                message += f"⚠️ <b>什麼情況跑?</b>\n{risk_brief}\n\n"
            
            message += "━━━━━━━━━━━━━━━━\n"
            message += "👇 點擊查看完整分析\n\n"
            
            # === BUILD DETAILED ANALYSIS (Hidden in spoiler) ===
            detailed = self._build_detailed_text(ai_data, signal, sentiment)
            
            # Wrap in spoiler tag
            message += f'<span class="tg-spoiler">{detailed}</span>'
            
            # === BUTTON ===
            keyboard = [[
                InlineKeyboardButton("📊 查看圖表", url="https://www.tradingview.com/chart/?symbol=BTCUSDT")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send message with HTML parsing
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
            logger.info(f"Sent signal: {action_text} (confidence: {confidence_score}/10)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send signal: {e}", exc_info=True)
            return False

    def _build_detailed_text(self, ai_data: Dict, signal: Dict, sentiment: Dict) -> str:
        """Build detailed analysis text for spoiler section."""
        # Extract data
        pattern_chars = ai_data.get('pattern_characteristics', [])
        current_assessment = ai_data.get('current_assessment', {})
        news_headlines = sentiment.get('news_headlines', []) if sentiment else []
        data_warnings = sentiment.get('data_warnings', []) if sentiment else []
        
        rsi = signal['indicators'].get('rsi') if signal.get('indicators') else None
        macd = signal['indicators'].get('macd') if signal.get('indicators') else None
        volume_change = signal['indicators'].get('volume_change', 0) if signal.get('indicators') else 0
        
        fear_greed_value = sentiment.get('fear_greed_value') if sentiment else None
        fear_greed_class = sentiment.get('fear_greed_class', 'Neutral') if sentiment else 'Neutral'
        inst_summary = sentiment.get('institutional_summary', {}) if sentiment else {}
        etf_net = inst_summary.get('etf_net_m') if inst_summary else None
        lsr_ratio = inst_summary.get('lsr_ratio') if inst_summary else None
        
        # Build detailed text
        text = "<b>📊 完整技術分析</b>\n\n"
        
        # Technical indicators
        text += "<b>技術指標</b>\n"
        if rsi is not None:
            text += f"RSI: {rsi:.0f}\n"
        if macd is not None:
            macd_text = "多頭" if macd > 0 else "空頭"
            text += f"MACD: {macd_text} ({macd:+.0f})\n"
        if volume_change:
            text += f"成交量: {volume_change:+.0f}%\n"
        if fear_greed_value is not None:
            text += f"恐懼指數: {fear_greed_value}/100 ({fear_greed_class})\n"
        
        # Institutional data
        if etf_net or lsr_ratio:
            text += "\n<b>機構數據</b>\n"
            if etf_net:
                text += f"ETF 淨流: ${etf_net:.0f}M\n"
            if lsr_ratio:
                text += f"多空比: {lsr_ratio:.2f}\n"
        if data_warnings:
            warning_line = html.escape(data_warnings[0])
            text += f"\n{warning_line}\n"
        
        text += "\n━━━━━━━━━━━━━━━━\n\n"

        # News headlines
        if news_headlines:
            text += "<b>📰 最新新聞</b>\n"
            for title in news_headlines[:3]:
                text += f"• {html.escape(title)}\n"
            text += "\n"
        
        # Pattern characteristics
        if pattern_chars:
            text += "<b>模式特徵</b>\n"
            for char in pattern_chars:
                text += f"• {html.escape(char)}\n"
            text += "\n"
        
        # Current setup assessment
        if current_assessment:
            text += "<b>🎯 本次評估</b>\n"
            
            if 'vs_typical' in current_assessment:
                text += f"對比: {html.escape(current_assessment['vs_typical'])}\n"
            
            if 'special_risk' in current_assessment:
                text += f"⚠️ {html.escape(current_assessment['special_risk'])}\n"
        
        return text

    def _get_confidence_emoji(self, confidence: int) -> str:
        """Get emoji for confidence level."""
        if confidence >= 9:
            return "🔥"
        elif confidence >= 7:
            return "✨"
        elif confidence >= 5:
            return "💫"
        else:
            return "⚠️"


# Test
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if not TELEGRAM_AVAILABLE:
        print("Error: python-telegram-bot is not installed", file=sys.stderr)
        sys.exit(1)
    
    try:
        notifier = TelegramNotifier()
        
        # Test signal
        test_sentiment = {
            'ai_advice_text': """訊號: HOLD\n強度: 2\n信心評分: 4\n入場: N/A\n目標: N/A\n停損: N/A\n風報比: N/A\n理由: 技術指標（RSI、MACD、OBV）普遍偏空，但ETF資金流入顯示機構看多。新聞提及宏觀壓力與槓桿解除，加劇賣壓。情緒指標為恐懼，但缺乏明確反彈訊號，多空比中性，故暫時觀望。\n倉位: 0%\n風險: 價格跌破 $68,000 情境。\n設定類型分析:\n類型: 無明確設定\n模式特徵:\n- 缺乏明確的技術或情緒訊號指引。\n- 市場處於觀望或不確定階段。\n- 交易者傾向於等待更清晰的入場點。\n本次評估:\n- 與典型案例相比: 較弱\n- 特殊風險: 宏觀經濟壓力持續，可能導致進一步的槓桿解除和價格下跌。\n""",
            'fear_greed_value': 17,
            'fear_greed_class': 'Extreme Fear',
            'institutional_summary': {
                'etf_net_m': 320,
                'lsr_ratio': 0.85
            }
        }
        
        test_signal = {
            'action': 'BUY',
            'strength': 5,
            'price': 78478,
            'indicators': {
                'rsi': 22,
                'macd': 160,
                'volume_change': 45
            }
        }
        
        asyncio.run(notifier.send_signal(test_signal, test_sentiment))
        print("✅ Test signal sent successfully!")
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
