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
            
            # Parse position/risk management
            position_match = re.search(r'倉位[:：]\s*(.+?)' + next_sections, ai_text_clean, re.DOTALL)
            if position_match:
                data['risk_management'] = position_match.group(1).strip()
            
            # Parse main risk
            risk_match = re.search(r'風險[:：]\s*(.+?)' + next_sections, ai_text_clean, re.DOTALL)
            if risk_match:
                data['main_risk'] = risk_match.group(1).strip()
            
            # Parse pattern type (legacy)
            pattern_type_match = re.search(r'\n類型[:：]\s*(.+?)(?=\n|模式特徵|$)', ai_text_clean)
            if pattern_type_match:
                data['pattern_type'] = pattern_type_match.group(1).strip()
            
            # Parse pattern characteristics (legacy)
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

            # Keep raw text for fallback display
            data['raw_text'] = ai_text_clean.strip()
            
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
        """Send signal with concise, decision-first summary."""
        try:
            # Extract core signal (from calculate_signal_strength)
            signal_action = signal.get('action', 'HOLD')
            signal_strength = int(signal.get('strength', 3) or 3)
            score = float(signal.get('score', 0) or 0)
            raw_score = float(signal.get('raw_score', 0) or 0)
            direction_score = int(signal.get('direction_score', 0) or 0)
            obv_trend = signal.get('obv_trend', 'flat')
            near_support = signal.get('near_support')
            near_resistance = signal.get('near_resistance')
            bouncing = signal.get('bouncing')
            atr_percent = float(signal.get('atr_percent', 0) or 0)
            component_scores = signal.get('component_scores', {}) or {}
            trade_plan = signal.get('trade_plan')

            # Action mapping (display)
            action_map = {'BUY': '買入', 'SELL': '賣出', 'HOLD': '觀望'}
            action_emoji = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡'}
            
            action_text = action_map.get(signal_action, '觀望')
            emoji = action_emoji.get(signal_action, '🟡')
            
            # === BUILD MESSAGE (HTML FORMAT) ===
            message = f"{emoji} <b>BTC {action_text}</b> (強度 {signal_strength}/5)\n"
            message += f"✅ <b>建議動作</b>: {self._action_guidance(signal_action, trade_plan)}\n"
            message += (
                f"評分: {score:.2f} (原始 {raw_score:.2f}) | 方向: {direction_score:+d}\n"
                f"OBV: {self._fmt_obv(obv_trend)} | 支撐: {self._fmt_flag(near_support)} | "
                f"壓力: {self._fmt_flag(near_resistance)} | 反彈: {self._fmt_flag(bouncing)} | "
                f"ATR%: {atr_percent:.2f}\n"
            )
            message += "━━━━━━━━━━━━━━━━\n"

            # Component scores
            message += "<b>分數拆解</b>\n"
            message += (
                f"趨勢 {self._fmt_score(component_scores.get('trend'))} | "
                f"動能 {self._fmt_score(component_scores.get('momentum'))} | "
                f"量能 {self._fmt_score(component_scores.get('volume'))} | "
                f"技術 {self._fmt_score(component_scores.get('technical'))}\n"
            )

            # Trade plan summary (if available)
            if trade_plan:
                message += "\n<b>交易計劃</b>\n"
                message += self._format_trade_plan_full(trade_plan)

            # Backtest section (if available)
            backtest_stats = sentiment.get('backtest_stats') if sentiment else None
            if backtest_stats and 'error' not in backtest_stats:
                message += "\n━━━━━━━━━━━━━━━━\n"
                message += self._format_backtest_section(backtest_stats)

            # Sentiment: Fear & Greed + Institutional + News
            message += "\n━━━━━━━━━━━━━━━━\n"
            message += self._format_sentiment_sections(sentiment, signal)

            # AI advice text (if available)
            ai_advice_text = sentiment.get('ai_advice_text') if sentiment else None
            if ai_advice_text:
                message += "\n━━━━━━━━━━━━━━━━\n"
                message += "<b>AI 建議</b>\n"
                message += f"{html.escape(str(ai_advice_text))}\n"
            
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
            
            logger.info(f"Sent signal: {action_text} (strength: {signal_strength}/5)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send signal: {e}", exc_info=True)
            return False

    def _format_sentiment_sections(self, sentiment: Optional[Dict], signal: Optional[Dict] = None) -> str:
        """Build Technical, Fear & Greed, Institutional Data, and News sections."""
        fear_greed_value = sentiment.get('fear_greed_value') if sentiment else None
        fear_greed_class = sentiment.get('fear_greed_class') if sentiment else None
        inst_summary = sentiment.get('institutional_summary', {}) if sentiment else {}
        news_headlines = sentiment.get('news_headlines', []) if sentiment else []
        tech_summary = sentiment.get('technical_summary', {}) if sentiment else {}

        text = ""

        # Enhanced Technical Indicators (4-category structure)
        text += "<b>技術指標</b>\n"
        if signal:
            text += self._format_technical_indicators_enhanced(tech_summary, signal)
            text += "\n"
        else:
            # Fallback to basic display
            rsi = tech_summary.get('rsi')
            macd = tech_summary.get('macd')
            signal_line = tech_summary.get('signal_line')
            volume_change = tech_summary.get('volume_change')

            rsi_text = f"RSI {rsi:.0f}" if rsi is not None else "RSI N/A"
            if macd is not None and signal_line is not None:
                macd_text = "MACD 多頭" if macd >= signal_line else "MACD 空頭"
            else:
                macd_text = "MACD N/A"
            text += f"{rsi_text} | {macd_text}\n"

            if volume_change is not None:
                text += f"成交量: {volume_change:+.0f}%\n"
            else:
                text += "成交量: N/A\n"

        # Fear & Greed
        text += "\n<b>Fear & Greed</b>\n"
        if fear_greed_value is not None:
            fg_class = html.escape(str(fear_greed_class or "N/A"))
            text += f"指數: {fear_greed_value}/100 ({fg_class})\n"
        else:
            text += "指數: N/A\n"

        # Institutional Data
        text += "\n<b>Institutional Data</b>\n"
        etf_net = inst_summary.get('etf_net_m')
        lsr_ratio = inst_summary.get('lsr_ratio')
        funding_rate_pct = inst_summary.get('funding_rate_pct')
        if etf_net is not None:
            text += f"ETF 淨流: {etf_net:+.0f}M\n"
        if lsr_ratio is not None:
            text += f"多空比: {lsr_ratio:.2f}\n"
        if funding_rate_pct is not None:
            text += f"Funding: {funding_rate_pct:+.3f}%\n"
        if etf_net is None and lsr_ratio is None and funding_rate_pct is None:
            text += "N/A\n"

        # Crypto News
        text += "\n<b>Crypto News</b>\n"
        if news_headlines:
            for title in news_headlines[:3]:
                text += f"• {html.escape(title)}\n"
        else:
            text += "N/A\n"

        return text

    def _format_trade_plan_full(self, trade_plan: Dict) -> str:
        """Format trade plan with all fields included."""
        lines = []

        # Market regime + volatility
        lines.append(f"市場型態: {self._fmt_text(trade_plan.get('market_regime'))}")
        lines.append(f"波動率: {self._fmt_text(trade_plan.get('volatility'))}")
        if trade_plan.get('atr_percent') is not None:
            lines.append(f"ATR%: {trade_plan.get('atr_percent'):.2f}")

        # Entries
        entries = trade_plan.get('entries', {})
        lines.append(
            "入場價格: 激進 "
            f"{self._fmt_price(entries.get('aggressive'))} | 保守 "
            f"{self._fmt_price(entries.get('conservative'))} | 理想 "
            f"{self._fmt_price(entries.get('ideal'))} | 掛單 "
            f"{self._fmt_price(entries.get('limit_order'))}"
        )
        lines.append(f"入場建議: {self._fmt_text(trade_plan.get('entry_recommendation'))}")

        # Stops
        stops = trade_plan.get('stops', {})
        lines.append(
            "停損: 硬 "
            f"{self._fmt_price(stops.get('hard_stop'))} | 軟 "
            f"{self._fmt_price(stops.get('soft_stop'))} | 移動 "
            f"{self._fmt_price(stops.get('trailing_stop'))} | 心理 "
            f"{self._fmt_price(stops.get('mental_stop'))}"
        )
        lines.append(f"停損建議: {self._fmt_text(trade_plan.get('stop_recommendation'))}")

        # Targets
        targets = trade_plan.get('targets', {})
        lines.append(
            "目標: T1 "
            f"{self._fmt_price(targets.get('T1'))} | T2 "
            f"{self._fmt_price(targets.get('T2'))} | T3 "
            f"{self._fmt_price(targets.get('T3'))} | Moon "
            f"{self._fmt_price(targets.get('moon'))}"
        )
        lines.append(f"目標建議: {self._fmt_text(trade_plan.get('target_recommendation'))}")

        # Risk reward
        rr = trade_plan.get('risk_reward_ratios', {})
        lines.append(
            "風報比: T1 "
            f"{self._fmt_score(rr.get('T1'))} | T2 "
            f"{self._fmt_score(rr.get('T2'))} | T3 "
            f"{self._fmt_score(rr.get('T3'))}"
        )
        lines.append(f"最低風報比: {self._fmt_score(trade_plan.get('min_acceptable_rr'))}")
        lines.append(f"最佳風報比: {self._fmt_score(trade_plan.get('actual_best_rr'))}")

        # Position sizing
        position = trade_plan.get('position_sizing', {})
        lines.append(
            "倉位: 凱利 "
            f"{self._fmt_percent(position.get('kelly_fraction'))} | 保守 "
            f"{self._fmt_percent(position.get('conservative'))} | 激進 "
            f"{self._fmt_percent(position.get('aggressive'))} | 建議 "
            f"{self._fmt_percent(position.get('recommended'))} | 最大風險 "
            f"{self._fmt_percent(position.get('max_risk_percent'), raw_percent=True)}"
        )
        lines.append(f"倉位建議: {self._fmt_text(trade_plan.get('position_recommendation'))}")
        kelly_source = position.get('kelly_source', '未知')
        lines.append(f"凱利依據: {self._fmt_text(kelly_source)}")

        # Pyramiding
        pyramiding = trade_plan.get('pyramiding', {})
        add_levels = pyramiding.get('add_on_levels', []) if pyramiding else []
        add_levels_text = ", ".join(self._fmt_price(p) for p in add_levels) if add_levels else "—"
        lines.append(
            "加碼: 啟用 "
            f"{self._fmt_flag(pyramiding.get('enabled'))} | 水位 "
            f"{add_levels_text} | 縮減 "
            f"{self._fmt_score(pyramiding.get('reduce_size_by'))}"
        )

        # Holding period
        holding = trade_plan.get('holding_period', {})
        lines.append(
            "持有期: 最短 "
            f"{self._fmt_days(holding.get('min_days'))} | 預期 "
            f"{self._fmt_days(holding.get('expected_days'))} | 最長 "
            f"{self._fmt_days(holding.get('max_days'))} | 型態 "
            f"{self._fmt_text(holding.get('regime_factor'))}"
        )
        lines.append(f"時間停損: {self._fmt_flag(trade_plan.get('time_stop_enabled'))}")

        # Exit strategy
        exit_strategy = trade_plan.get('exit_strategy', {})
        lines.append(
            "出場策略: T1 "
            f"{self._fmt_text(exit_strategy.get('T1_action'))} | T2 "
            f"{self._fmt_text(exit_strategy.get('T2_action'))} | T3 "
            f"{self._fmt_text(exit_strategy.get('T3_action'))} | 停損 "
            f"{self._fmt_text(exit_strategy.get('stop_hit'))} | 時間 "
            f"{self._fmt_text(exit_strategy.get('time_stop'))} | 反轉 "
            f"{self._fmt_text(exit_strategy.get('signal_reversal'))}"
        )

        # Risk warnings
        warnings = trade_plan.get('risk_warnings', [])
        if warnings:
            for w in warnings:
                lines.append(f"風險提示: {html.escape(str(w))}")
        else:
            lines.append("風險提示: —")

        # Expectancy
        if trade_plan.get('estimated_win_rate') is not None:
            lines.append(f"預估勝率: {trade_plan.get('estimated_win_rate'):.1f}%")
        else:
            lines.append("預估勝率: —")
        if trade_plan.get('expected_return') is not None:
            lines.append(f"期望報酬: {trade_plan.get('expected_return'):.1f}%")
        else:
            lines.append("期望報酬: —")

        return "\n".join(lines) + "\n"

    def _fmt_score(self, value: Optional[float]) -> str:
        if value is None:
            return "—"
        return f"{float(value):.1f}"

    def _fmt_price(self, value: Optional[float]) -> str:
        if value is None:
            return "—"
        return f"${float(value):,.2f}"

    def _fmt_days(self, value: Optional[int]) -> str:
        if value is None:
            return "—"
        return f"{int(value)}d"

    def _fmt_text(self, value: Optional[str]) -> str:
        if value is None or value == "":
            return "—"
        return html.escape(str(value))

    def _fmt_percent(self, value: Optional[float], raw_percent: bool = False) -> str:
        if value is None:
            return "—"
        if raw_percent:
            return f"{float(value):.1f}%"
        return f"{float(value) * 100:.1f}%"

    def _fmt_obv(self, obv_trend: str) -> str:
        if obv_trend == 'up':
            return "上升"
        if obv_trend == 'down':
            return "下降"
        return "持平"

    def _fmt_flag(self, value: Optional[bool]) -> str:
        if value is True:
            return "是"
        if value is False:
            return "否"
        return "—"

    def _action_guidance(self, action: str, trade_plan: Optional[Dict]) -> str:
        if action == 'HOLD' or not trade_plan:
            return "觀望，等待更佳訊號"

        entries = trade_plan.get('entries', {}) if trade_plan else {}
        stops = trade_plan.get('stops', {}) if trade_plan else {}
        targets = trade_plan.get('targets', {}) if trade_plan else {}
        pos_rec = trade_plan.get('position_recommendation')
        position = trade_plan.get('position_sizing', {}) if trade_plan else {}

        entry = self._fmt_price(entries.get('conservative') or entries.get('aggressive'))
        stop = self._fmt_price(stops.get('hard_stop'))
        t1 = self._fmt_price(targets.get('T1'))
        size = pos_rec
        if not size and position.get('recommended') is not None:
            size = f"{position.get('recommended') * 100:.1f}%"
        size = size or "—"

        if action == 'BUY':
            return f"在 {entry} 附近分批買入，硬停損 {stop}，T1 {t1}，倉位 {size}"
        if action == 'SELL':
            return f"在 {entry} 附近分批賣出，硬停損 {stop}，T1 {t1}，倉位 {size}"
        return "觀望，等待更佳訊號"

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

    def _format_technical_indicators_enhanced(self, tech_summary: Dict, signal: Dict) -> str:
        """Format enhanced technical indicators with 4-category structure (Trend/Momentum/Position/Volume)."""
        lines = []

        # Extract indicators
        indicators = signal.get('indicators', {})
        ema_12 = indicators.get('ema_12')
        ema_26 = indicators.get('ema_26')
        ema_50 = indicators.get('ema_50')
        ema_200 = indicators.get('ema_200')
        adx = indicators.get('adx')
        rsi = tech_summary.get('rsi')
        stoch_k = indicators.get('stoch_k')
        stoch_d = indicators.get('stoch_d')
        bb_upper = indicators.get('bb_upper')
        bb_middle = indicators.get('bb_middle')
        bb_lower = indicators.get('bb_lower')
        support = indicators.get('support')
        resistance = indicators.get('resistance')
        price = signal.get('price')
        volume_change = tech_summary.get('volume_change')
        obv_trend = signal.get('obv_trend')

        # Trend indicators
        trend_parts = []
        if ema_12 and ema_26 and ema_50 and ema_200:
            if ema_12 > ema_26 > ema_50 > ema_200:
                trend_parts.append("EMA 多頭排列")
            elif ema_12 < ema_26 < ema_50 < ema_200:
                trend_parts.append("EMA 空頭排列")
            else:
                trend_parts.append("EMA 混亂")

        if adx is not None:
            if adx > 25:
                trend_parts.append(f"ADX {adx:.1f} (強趨勢)")
            elif adx > 20:
                trend_parts.append(f"ADX {adx:.1f} (弱趨勢)")
            else:
                trend_parts.append(f"ADX {adx:.1f} (盤整)")

        if trend_parts:
            lines.append("【趨勢】" + " | ".join(trend_parts))

        # Momentum indicators
        momentum_parts = []
        if rsi is not None:
            if rsi < 30:
                momentum_parts.append(f"RSI {rsi:.0f} (超賣)")
            elif rsi > 70:
                momentum_parts.append(f"RSI {rsi:.0f} (超買)")
            elif rsi < 40:
                momentum_parts.append(f"RSI {rsi:.0f} (偏空)")
            elif rsi > 60:
                momentum_parts.append(f"RSI {rsi:.0f} (偏多)")
            else:
                momentum_parts.append(f"RSI {rsi:.0f} (中性)")

        if stoch_k is not None and stoch_d is not None:
            if stoch_k > stoch_d:
                momentum_parts.append(f"隨機 {stoch_k:.0f}↗{stoch_d:.0f} (金叉)")
            else:
                momentum_parts.append(f"隨機 {stoch_k:.0f}↘{stoch_d:.0f} (死叉)")

        if momentum_parts:
            lines.append("【動能】" + " | ".join(momentum_parts))

        # Position indicators (Bollinger Bands + Support/Resistance)
        position_parts = []
        if price and bb_upper and bb_middle and bb_lower:
            if price > bb_upper:
                position_parts.append("布林 上軌突破")
            elif price < bb_lower:
                position_parts.append("布林 下軌突破")
            else:
                band_range = bb_upper - bb_lower
                position_pct = ((price - bb_lower) / band_range * 100) if band_range > 0 else 50
                if position_pct > 80:
                    position_parts.append(f"布林 上軌-{100-position_pct:.0f}%")
                elif position_pct < 20:
                    position_parts.append(f"布林 下軌+{position_pct:.0f}%")
                else:
                    position_parts.append("布林 中軌")

        if support:
            position_parts.append(f"支撐 {support:,.0f}")
        if resistance:
            position_parts.append(f"壓力 {resistance:,.0f}")

        if position_parts:
            lines.append("【位置】" + " | ".join(position_parts))

        # Volume indicators
        if volume_change is not None:
            obv_text = self._fmt_obv(obv_trend)
            lines.append(f"【量能】成交量 {volume_change:+.0f}% | OBV {obv_text}")

        return "\n".join(lines)

    def _calculate_confidence(self, total_trades: int) -> str:
        """Statistical confidence based on sample size."""
        if total_trades >= 30:
            return "高"
        elif total_trades >= 15:
            return "中"
        elif total_trades >= 5:
            return "低"
        else:
            return "極低"

    def _format_equity_sparkline(self, equity_curve: list, bins: int = 10) -> str:
        """Convert equity curve to Unicode sparkline."""
        if not equity_curve or len(equity_curve) < 2:
            return "—"

        step = max(1, len(equity_curve) // bins)
        sampled = [equity_curve[i * step] for i in range(min(bins, len(equity_curve) // step))]

        if len(sampled) < 2:
            return "—"

        min_val = min(sampled)
        max_val = max(sampled)
        if max_val == min_val:
            return "▅" * len(sampled)

        blocks = " ▁▂▃▄▅▆▇█"
        normalized = [(v - min_val) / (max_val - min_val) * 8 for v in sampled]
        return "".join(blocks[int(n)] for n in normalized)

    def _format_backtest_section(self, backtest_stats: Optional[Dict]) -> str:
        """Format backtest performance section."""
        if not backtest_stats or 'error' in backtest_stats:
            return ""

        wins = backtest_stats.get('wins', 0)
        losses = backtest_stats.get('losses', 0)
        total = wins + losses
        win_rate = backtest_stats.get('win_rate', 0)
        avg_profit = backtest_stats.get('avg_profit', 0)
        best = backtest_stats.get('best_trade', 0)
        worst = backtest_stats.get('worst_trade', 0)
        max_dd = backtest_stats.get('max_drawdown', 0)
        total_return = backtest_stats.get('total_return', 0)
        equity_curve = backtest_stats.get('equity_curve', [])

        confidence = self._calculate_confidence(total)
        sparkline = self._format_equity_sparkline(equity_curve)

        lines = []
        lines.append("<b>回測績效 (30天)</b>")
        lines.append(
            f"勝率: {win_rate:.1f}% ({wins}勝/{losses}負) | "
            f"平均盈虧: {avg_profit:+.1f}%"
        )
        lines.append(
            f"最佳: {best:+.1f}% | 最差: {worst:+.1f}% | "
            f"最大回撤: {max_dd:.1f}%"
        )
        lines.append(
            f"總報酬: {total_return:+.1f}% | "
            f"信心: {confidence} ({total}筆樣本)"
        )
        if sparkline != "—":
            lines.append(f"📊 權益曲線: {sparkline}")

        return "\n".join(lines) + "\n"


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
