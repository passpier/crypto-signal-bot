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
            next_sections = r'(?=\n?倉位|\n?風險|\n?設定類型分析|\n?類型|\n?模式特徵|\n?典型表現|\n?本次評估|$)'
            
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
                r'模式特徵[:：]\s*(.+?)(?=典型表現|本次評估|$)',
                ai_text_clean,
                re.DOTALL
            )
            if char_section:
                char_text = char_section.group(1)
                char_items = re.findall(r'(?:[-•\d]+\.?)\s*(.+?)(?=\n|$)', char_text)
                characteristics = [c.strip() for c in char_items if c.strip()]
            data['pattern_characteristics'] = characteristics
            
            # Parse typical performance
            typical_perf = {}
            
            win_rate_match = re.search(r'勝率(?:範圍)?[:：]\s*([\d.]+)[-~]([\d.]+)%', ai_text_clean)
            if win_rate_match:
                typical_perf['win_rate_min'] = float(win_rate_match.group(1))
                typical_perf['win_rate_max'] = float(win_rate_match.group(2))
            
            holding_perf_match = re.search(r'平均持有[:：]\s*(\d+)[-~](\d+)天', ai_text_clean)
            if holding_perf_match:
                typical_perf['holding_days_min'] = int(holding_perf_match.group(1))
                typical_perf['holding_days_max'] = int(holding_perf_match.group(2))
            
            drawdown_match = re.search(r'常見回撤[:：]\s*-?([\d.]+)%?\s*(?:to|-|~)\s*-?([\d.]+)%', ai_text_clean)
            if drawdown_match:
                typical_perf['drawdown_min'] = float(drawdown_match.group(1))
                typical_perf['drawdown_max'] = float(drawdown_match.group(2))
            
            entry_timing_match = re.search(r'最佳進場時機[:：]\s*(.+?)(?=\n|常見失敗)', ai_text_clean)
            if entry_timing_match:
                typical_perf['best_entry_timing'] = entry_timing_match.group(1).strip()
            
            if typical_perf:
                data['typical_performance'] = typical_perf
            
            # Parse failure reasons
            failure_reasons = []
            failure_section = re.search(
                r'常見失敗原因[:：]\s*(.+?)(?=本次評估|$)',
                ai_text_clean,
                re.DOTALL
            )
            if failure_section:
                failure_text = failure_section.group(1)
                failure_items = re.findall(r'(?:[-•\d]+\.?)\s*(.+?)(?=\n|$)', failure_text)
                failure_reasons = [f.strip() for f in failure_items if f.strip()]
            data['failure_reasons'] = failure_reasons
            
            # Parse current assessment
            assessment = {}
            
            comparison_match = re.search(r'與典型案例相比[:：]\s*(.+?)(?=\n|特殊風險)', ai_text_clean)
            if comparison_match:
                assessment['vs_typical'] = comparison_match.group(1).strip()
            
            special_risk_match = re.search(r'特殊風險[:：]\s*(.+?)(?=\n|成功機率|$)', ai_text_clean)
            if special_risk_match:
                assessment['special_risk'] = special_risk_match.group(1).strip()
            
            success_prob_match = re.search(r'成功機率[:：]\s*([\d.]+)[-~]?([\d.]+)?%', ai_text_clean)
            if success_prob_match:
                prob_min = float(success_prob_match.group(1))
                prob_max = float(success_prob_match.group(2)) if success_prob_match.group(2) else prob_min
                assessment['success_probability_min'] = prob_min
                assessment['success_probability_max'] = prob_max
            
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
            
            pattern_type = ai_data.get('pattern_type', '')
            typical_perf = ai_data.get('typical_performance', {})
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
            message += f"💰 現價: ${current_price:,.0f}\n"
            
            if entry_range:
                entry_low = entry_range.get('low', 0)
                entry_high = entry_range.get('high', 0)
                if entry_low and entry_high:
                    message += f"📍 入場: ${entry_low:,.0f}-${entry_high:,.0f}\n"
            
            if target_price and len(target_price) > 0:
                target = target_price[0]
                target_price_value = target.get('price', 0)
                target_pct = target.get('percentage', 0)
                if target_price_value > 0:
                    message += f"🎯 目標: ${target_price_value:,.0f} (+{target_pct:.1f}%)\n"
            
            if stop_loss:
                stop_price = stop_loss.get('price', 0)
                stop_pct = stop_loss.get('percentage', 0)
                if stop_price > 0:
                    message += f"🛡 停損: ${stop_price:,.0f} (-{stop_pct:.1f}%)\n"
            
            # Holding period
            holding = ai_data.get('expected_holding_days', {})
            if holding:
                min_days = holding.get('min', 0)
                max_days = holding.get('max', 0)
                if min_days and max_days:
                    if min_days == max_days:
                        message += f"⏱ 持有: {min_days}天\n"
                    else:
                        message += f"⏱ 持有: {min_days}-{max_days}天\n"
            
            message += "━━━━━━━━━━━━━━━━\n"
            
            # Pattern + Confidence (one line)
            win_rate_text = ""
            if typical_perf.get('win_rate_min'):
                win_min = typical_perf['win_rate_min']
                win_max = typical_perf['win_rate_max']
                win_rate_text = f" | 勝率: {win_min:.0f}-{win_max:.0f}%"
            
            if pattern_type:
                message += f"📊 設定: {html.escape(pattern_type)}\n"
            message += f"✨ 信心: {confidence_score}/10{win_rate_text}\n\n"
            
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
        typical_perf = ai_data.get('typical_performance', {})
        failure_reasons = ai_data.get('failure_reasons', [])
        current_assessment = ai_data.get('current_assessment', {})
        
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
        
        text += "\n━━━━━━━━━━━━━━━━\n\n"
        
        # Pattern characteristics
        if pattern_chars:
            text += "<b>模式特徵</b>\n"
            for char in pattern_chars:
                text += f"• {html.escape(char)}\n"
            text += "\n"
        
        # Typical performance
        if typical_perf:
            text += "<b>典型表現</b>\n"
            
            if 'win_rate_min' in typical_perf:
                win_min = typical_perf['win_rate_min']
                win_max = typical_perf['win_rate_max']
                avg_win = (win_min + win_max) / 2
                
                # Win rate emoji
                if avg_win >= 70:
                    win_emoji = "🟢"
                elif avg_win >= 55:
                    win_emoji = "🟡"
                else:
                    win_emoji = "🔴"
                
                text += f"{win_emoji} 勝率: {win_min:.0f}-{win_max:.0f}%\n"
            
            if 'holding_days_min' in typical_perf:
                text += f"⏱ 持有: {typical_perf['holding_days_min']}-{typical_perf['holding_days_max']}天\n"
            
            if 'drawdown_min' in typical_perf:
                text += f"📉 回撤: -{typical_perf['drawdown_min']:.1f}% ~ -{typical_perf['drawdown_max']:.1f}%\n"
            
            if 'best_entry_timing' in typical_perf:
                text += f"✅ 進場: {html.escape(typical_perf['best_entry_timing'])}\n"
            
            text += "\n"
        
        # Common failure scenarios
        if failure_reasons:
            text += "<b>⚠️ 常見陷阱</b>\n"
            for i, reason in enumerate(failure_reasons, 1):
                text += f"{i}. {html.escape(reason)}\n"
            text += "\n"
        
        # Current setup assessment
        if current_assessment:
            text += "<b>🎯 本次評估</b>\n"
            
            if 'vs_typical' in current_assessment:
                text += f"對比: {html.escape(current_assessment['vs_typical'])}\n"
            
            if 'success_probability_min' in current_assessment:
                prob_min = current_assessment['success_probability_min']
                prob_max = current_assessment['success_probability_max']
                if prob_min == prob_max:
                    text += f"機率: {prob_min:.0f}%\n"
                else:
                    text += f"機率: {prob_min:.0f}-{prob_max:.0f}%\n"
            
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
            'ai_advice_text': """訊號: BUY
強度: 5
信心評分: 9/10
入場: 77500-78000
目標: 80500 (+3.2%)
停損: 76800 (-2.1%)
預期時間: 3-7天達標
風報比: 1:1.5
理由: RSI極度超賣形成背離，恐懼指數極端恐慌，ETF大量流入
倉位: 30%分3批進場，第一批當前價位，第二批-1.5%加碼
風險: 跌破76500確認空頭延續

設定類型分析:
類型: 極度超賣反彈
模式特徵:
- RSI <25 且形成背離
- 恐懼指數 <20 極端恐慌
- 機構資金逆向流入
典型表現:
- 勝率範圍: 65-75%
- 平均持有: 3-7天
- 常見回撤: -2% to -4%
- 最佳進場時機: 恐慌最高點，成交量萎縮後放大
- 常見失敗原因: 1. 恐慌未結束，繼續下探 2. 反彈無量，誘多陷阱
本次評估:
- 與典型案例相比: 更強 (機構ETF流入$320M)
- 特殊風險: 若跌破76500，恐慌加劇
- 成功機率: 70-80%""",
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