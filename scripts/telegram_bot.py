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

    # ─── Zone builders ────────────────────────────────────────────────────────

    def _build_zone1_header(self, signal_action: str, signal_strength: int, price: Optional[float], atr_percent: float) -> str:
        """Zone 1: Signal header — action, strength stars, current price, ATR."""
        action_map = {'BUY': '買入', 'SELL': '賣出', 'HOLD': '觀望'}
        action_emoji = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡'}

        emoji = action_emoji.get(signal_action, '🟡')
        action_text = action_map.get(signal_action, '觀望')
        stars = '★' * signal_strength + '☆' * (5 - signal_strength)

        price_text = f"${price:,.0f}" if price else "N/A"
        atr_text = f"ATR {atr_percent:.1f}%" if atr_percent else ""

        line1 = f"{emoji} <b>BTC {action_text}</b>  {stars} ({signal_strength}/5)"
        line2 = f"💰 現價: <b>{price_text}</b>"
        if atr_text:
            line2 += f"  |  {atr_text}"
        return line1 + "\n" + line2 + "\n"

    def _build_zone2_execution(self, trade_plan: Optional[Dict], signal_action: str) -> str:
        """Zone 2: Trade execution — entry, stop loss, targets, risk-reward, position."""
        if not trade_plan or signal_action == 'HOLD':
            return "▸ 操作: 觀望，等待更佳訊號\n"

        entries = trade_plan.get('entries', {}) or {}
        stops = trade_plan.get('stops', {}) or {}
        targets = trade_plan.get('targets', {}) or {}
        rr = trade_plan.get('risk_reward_ratios', {}) or {}
        position = trade_plan.get('position_sizing', {}) or {}

        lines = []

        # Entry range: conservative ~ aggressive
        entry_low = entries.get('conservative') or entries.get('aggressive')
        entry_high = entries.get('aggressive') or entries.get('conservative')
        if entry_low and entry_high and entry_low != entry_high:
            lo, hi = (entry_low, entry_high) if entry_low <= entry_high else (entry_high, entry_low)
            lines.append(f"▸ 入場  {self._fmt_price(lo)} – {self._fmt_price(hi)}  (保守優先)")
        elif entry_low:
            lines.append(f"▸ 入場  {self._fmt_price(entry_low)}")

        # Stop loss (hard stop with percentage)
        hard_stop = stops.get('hard_stop')
        if hard_stop:
            stop_pct = trade_plan.get('stop_loss_pct')
            pct_text = f"  (-{abs(stop_pct):.1f}%)" if stop_pct else ""
            lines.append(f"▸ 停損  {self._fmt_price(hard_stop)}{pct_text}  ← 硬停損")

        # Targets T1 / T2
        t1 = targets.get('T1')
        t2 = targets.get('T2')
        t3 = targets.get('T3')
        if t1 or t2:
            target_parts = []
            if t1:
                rr_t1 = rr.get('T1')
                rr_text = f"  RR {rr_t1:.1f}" if rr_t1 else ""
                target_parts.append(f"T1 {self._fmt_price(t1)}{rr_text}")
            if t2:
                rr_t2 = rr.get('T2')
                rr_text = f"  RR {rr_t2:.1f}" if rr_t2 else ""
                target_parts.append(f"T2 {self._fmt_price(t2)}{rr_text}")
            if t3:
                target_parts.append(f"T3 {self._fmt_price(t3)}")
            lines.append("▸ 目標  " + "  |  ".join(target_parts))

        # Position sizing
        recommended = position.get('recommended')
        kelly = position.get('kelly_fraction')
        if recommended is not None:
            pos_text = f"{recommended * 100:.1f}%"
            kelly_text = f"  (Kelly: {kelly * 100:.1f}%)" if kelly else ""
            lines.append(f"▸ 倉位  {pos_text}{kelly_text}")
        elif trade_plan.get('position_recommendation'):
            lines.append(f"▸ 倉位  {html.escape(str(trade_plan['position_recommendation']))}")

        return "\n".join(lines) + "\n" if lines else ""

    def _build_zone3_reason(self, ai_advice_text: Optional[str], component_scores: Dict, signal_action: str) -> str:
        """Zone 3: 1-line reason extracted from AI text or generated from scores."""
        reason = self._format_signal_reason(ai_advice_text, component_scores, signal_action)
        if reason:
            return f"📌 理由: {reason}\n"
        return ""

    def _build_zone4_technicals(self, tech_summary: Dict, signal: Dict) -> str:
        """Zone 4: Technical snapshot using the 4-category indicator formatter."""
        lines = ["<b>技術指標</b>"]
        indicator_text = self._format_technical_indicators_enhanced(tech_summary, signal)
        if indicator_text:
            lines.append(indicator_text)
        return "\n".join(lines) + "\n"

    def _build_zone5_market_context(self, sentiment: Optional[Dict]) -> str:
        """Zone 5: Market context — Fear & Greed, Institutional, News."""
        return self._format_market_context(sentiment)

    def _build_zone6_journal(self, journal_stats: Optional[Dict]) -> str:
        """Zone 6: Live journal — always shown (placeholder if no data yet)."""
        return self._format_journal_section(journal_stats)

    def _build_zone6_backtest(self, backtest_stats: Optional[Dict]) -> str:
        """Zone 7: Backtest performance (only if available)."""
        if not backtest_stats or 'error' in backtest_stats:
            return ""
        return self._format_backtest_section(backtest_stats)

    def _build_zone7_ai(self, ai_advice_text: Optional[str]) -> str:
        """Zone 7: Condensed AI analysis (narrative only, no duplicate structured fields)."""
        if not ai_advice_text:
            return ""
        condensed = self._format_ai_analysis(ai_advice_text)
        if condensed:
            return f"🤖 <b>AI 分析</b>\n{condensed}\n"
        return ""

    # ─── Main send method ─────────────────────────────────────────────────────

    async def send_signal(
        self,
        signal: Dict,
        sentiment: Optional[Dict] = None,
    ) -> bool:
        """Send signal with decision-first, 7-zone structured message."""
        try:
            signal_action = signal.get('action', 'HOLD')
            signal_strength = int(signal.get('strength', 3) or 3)
            price = signal.get('price')
            atr_percent = float(signal.get('atr_percent', 0) or 0)
            component_scores = signal.get('component_scores', {}) or {}
            trade_plan = signal.get('trade_plan')
            tech_summary = sentiment.get('technical_summary', {}) if sentiment else {}
            backtest_stats = sentiment.get('backtest_stats') if sentiment else None
            journal_stats = sentiment.get('journal_stats') if sentiment else None
            ai_advice_text = sentiment.get('ai_advice_text') if sentiment else None

            # Build each zone
            sep = "─────────────────\n"

            message = self._build_zone1_header(signal_action, signal_strength, price, atr_percent)
            message += sep

            zone2 = self._build_zone2_execution(trade_plan, signal_action)
            if zone2:
                message += zone2
                message += sep

            zone3 = self._build_zone3_reason(ai_advice_text, component_scores, signal_action)
            if zone3:
                message += zone3
                message += sep

            message += self._build_zone4_technicals(tech_summary, signal)
            message += sep

            zone5 = self._build_zone5_market_context(sentiment)
            if zone5:
                message += zone5
                message += sep

            # Zone 6: Live journal (always shown — placeholder if no data yet)
            zone6_journal = self._build_zone6_journal(journal_stats)
            message += zone6_journal
            message += sep

            # Zone 7: Simulation backtest (skip if unavailable)
            zone7_backtest = self._build_zone6_backtest(backtest_stats)
            if zone7_backtest:
                message += zone7_backtest
                message += sep

            # Zone 8: AI analysis (length-limited)
            zone8_ai = self._build_zone7_ai(ai_advice_text)
            if zone8_ai:
                remaining = 4096 - len(message) - 50
                if remaining > 100:
                    message += zone8_ai[:remaining]

            # Single TradingView button
            keyboard = [[
                InlineKeyboardButton("📊 查看圖表", url="https://www.tradingview.com/chart/?symbol=BTCUSDT")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

            action_map = {'BUY': '買入', 'SELL': '賣出', 'HOLD': '觀望'}
            logger.info(f"Sent signal: {action_map.get(signal_action, signal_action)} (strength: {signal_strength}/5)")
            return True

        except Exception as e:
            logger.error(f"Failed to send signal: {e}", exc_info=True)
            return False

    # ─── Zone helper formatters ───────────────────────────────────────────────

    def _format_signal_reason(self, ai_advice_text: Optional[str], component_scores: Dict, signal_action: str) -> str:
        """Extract 1-line reason: parse 理由 from AI text, else derive from component scores."""
        # Try to extract from AI text
        if ai_advice_text:
            clean = ai_advice_text.replace('\\n', '\n')
            match = re.search(r'理由[:：]\s*(.+?)(?:\n|倉位|風險|$)', clean, re.DOTALL)
            if match:
                reason = match.group(1).strip()
                # Trim to one line/sentence
                reason = re.split(r'[。\n]', reason)[0].strip()
                if reason:
                    return html.escape(reason)

        # Fallback: derive from component scores
        if not component_scores:
            return ""
        parts = []
        trend = component_scores.get('trend', 0) or 0
        momentum = component_scores.get('momentum', 0) or 0
        volume = component_scores.get('volume', 0) or 0
        technical = component_scores.get('technical', 0) or 0

        if signal_action == 'BUY':
            if trend > 0:
                parts.append("趨勢看多")
            if momentum > 0:
                parts.append("動能轉強")
            if volume > 0:
                parts.append("量能配合")
        elif signal_action == 'SELL':
            if trend < 0:
                parts.append("趨勢看空")
            if momentum < 0:
                parts.append("動能轉弱")
            if volume < 0:
                parts.append("量能萎縮")
        else:
            if abs(trend) < 0.5 and abs(momentum) < 0.5:
                parts.append("訊號中性")

        return "、".join(parts) if parts else ""

    def _format_ai_analysis(self, ai_text: str) -> str:
        """Condense AI advice text: keep narrative reasoning, strip duplicate structured fields."""
        if not ai_text:
            return ""

        clean = ai_text.replace('\\n', '\n')

        # Strip structured fields that are already shown in Zones 1-2
        structured_fields = r'^(訊號|強度|信心評分|入場|目標|停損|風報比|持有|倉位)[:：].*$'
        lines = clean.splitlines()
        narrative_lines = [
            line for line in lines
            if not re.match(structured_fields, line.strip())
        ]

        # Keep 理由, 風險, and narrative paragraphs; skip blank runs
        result_lines = []
        for line in narrative_lines:
            stripped = line.strip()
            if not stripped:
                if result_lines and result_lines[-1] != "":
                    result_lines.append("")
            else:
                result_lines.append(stripped)

        condensed = "\n".join(result_lines).strip()

        # Cap length
        if len(condensed) > 300:
            condensed = condensed[:297] + "…"

        return html.escape(condensed) if condensed else ""

    def _format_market_context(self, sentiment: Optional[Dict]) -> str:
        """Zone 5: Fear & Greed + Institutional + News — clean single block."""
        if not sentiment:
            return ""

        fear_greed_value = sentiment.get('fear_greed_value')
        fear_greed_class = sentiment.get('fear_greed_class')
        inst_summary = sentiment.get('institutional_summary', {}) or {}
        news_headlines = sentiment.get('news_headlines', []) or []

        lines = ["<b>市場情緒</b>"]

        # Fear & Greed
        if fear_greed_value is not None:
            fg_class = html.escape(str(fear_greed_class or "N/A"))
            lines.append(f"Fear & Greed  {fear_greed_value}/100 — {fg_class}")
        else:
            lines.append("Fear & Greed  N/A")

        # Institutional data on one line
        inst_parts = []
        etf_net = inst_summary.get('etf_net_m')
        lsr_ratio = inst_summary.get('lsr_ratio')
        funding_rate_pct = inst_summary.get('funding_rate_pct')

        if etf_net is not None:
            sign = "+" if etf_net >= 0 else ""
            inst_parts.append(f"ETF 淨流 {sign}{etf_net:.0f}M")
        if lsr_ratio is not None:
            inst_parts.append(f"多空比 {lsr_ratio:.2f}")
        if funding_rate_pct is not None:
            sign = "+" if funding_rate_pct >= 0 else ""
            inst_parts.append(f"Funding {sign}{funding_rate_pct:.3f}%")

        if inst_parts:
            lines.append("  |  ".join(inst_parts))

        # News headlines
        if news_headlines:
            lines.append("")
            for title in news_headlines[:2]:
                lines.append(f"• {html.escape(str(title))}")

        return "\n".join(lines) + "\n"

    def _format_technical_indicators_enhanced(self, tech_summary: Dict, signal: Dict) -> str:
        """Format technical indicators with 4-category structure (Trend/Momentum/Position/Volume)."""
        lines = []

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

        # Trend
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

        # Momentum
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

        # Position (Bollinger Bands + Support/Resistance)
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

        # Volume
        if volume_change is not None:
            obv_text = self._fmt_obv(obv_trend)
            lines.append(f"【量能】成交量 {volume_change:+.0f}% | OBV {obv_text}")

        return "\n".join(lines)

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

        lines = ["<b>回測績效 (近60天)</b>"]
        lines.append(
            f"勝率 {win_rate:.1f}% ({wins}勝/{losses}負)  平均 {avg_profit:+.1f}%"
        )
        lines.append(
            f"最佳 {best:+.1f}%  最差 {worst:+.1f}%  最大回撤 {max_dd:.1f}%  總報酬 {total_return:+.1f}%"
        )
        lines.append(f"信心 {confidence} ({total}筆)")
        if sparkline != "—":
            lines.append(f"權益曲線: {sparkline}")

        return "\n".join(lines) + "\n"

    def _format_journal_section(self, journal_stats: Optional[Dict]) -> str:
        """Format live trade journal performance section."""
        lines = ["<b>實際訊號績效 (近30天)</b>"]
        if not journal_stats:
            lines.append("尚無實際交易記錄")
            return "\n".join(lines) + "\n"

        wins = journal_stats.get('wins', 0)
        losses = journal_stats.get('losses', 0)
        total = wins + losses
        win_rate = journal_stats.get('win_rate', 0)
        avg_profit = journal_stats.get('avg_profit', 0)
        best = journal_stats.get('best_trade', 0)
        worst = journal_stats.get('worst_trade', 0)
        max_dd = journal_stats.get('max_drawdown', 0)
        total_return = journal_stats.get('total_return', 0)
        equity_curve = journal_stats.get('equity_curve', [])
        expired_count = journal_stats.get('expired_count', 0)

        confidence = self._calculate_confidence(total)
        sparkline = self._format_equity_sparkline(equity_curve)

        lines.append(
            f"勝率 {win_rate:.1f}% ({wins}勝/{losses}負)  平均 {avg_profit:+.1f}%"
        )
        lines.append(
            f"最佳 {best:+.1f}%  最差 {worst:+.1f}%  最大回撤 {max_dd:.1f}%  總報酬 {total_return:+.1f}%"
        )
        expired_text = f"  逾期 {expired_count}筆" if expired_count else ""
        lines.append(f"信心 {confidence} ({total}筆){expired_text}")
        if sparkline != "—":
            lines.append(f"權益曲線: {sparkline}")

        return "\n".join(lines) + "\n"

    # ─── Legacy parser (kept for potential future use) ────────────────────────

    def _parse_text_signal(self, ai_text: str) -> Dict:
        """Parse structured text with tolerance for formatting variations."""
        if not ai_text or not ai_text.strip():
            return {}

        try:
            data = {}

            signal_match = re.search(r'訊號[:：]\s*(BUY|SELL|HOLD|買入|賣出|觀望)', ai_text, re.IGNORECASE)
            if signal_match:
                signal_map = {'買入': 'BUY', '賣出': 'SELL', '觀望': 'HOLD'}
                raw_signal = signal_match.group(1)
                data['signal'] = signal_map.get(raw_signal, raw_signal.upper())

            strength_match = re.search(r'強度[:：]\s*(\d)', ai_text)
            if strength_match:
                data['strength'] = int(strength_match.group(1))

            confidence_match = re.search(r'信心評分[:：]\s*(\d+)(?:/10)?', ai_text)
            if confidence_match:
                confidence = int(confidence_match.group(1))
                data['confidence'] = max(1, min(10, confidence))

            entry_match = re.search(r'入場[:：]\s*\$?([\d,]+)\s*[-~]\s*\$?([\d,]+)', ai_text)
            if entry_match:
                data['entry_range'] = {
                    'low': float(entry_match.group(1).replace(',', '')),
                    'high': float(entry_match.group(2).replace(',', ''))
                }

            target_match = re.search(r'目標[:：]\s*\$?([\d,]+)\s*\(([+-]?[\d.]+)%\)', ai_text)
            if target_match:
                price = float(target_match.group(1).replace(',', ''))
                pct = abs(float(target_match.group(2)))
                data['target_price'] = [{'price': price, 'percentage': pct}]

            stop_match = re.search(r'停損[:：]\s*\$?([\d,]+)\s*\(([+-]?[\d.]+)%\)', ai_text)
            if stop_match:
                price = float(stop_match.group(1).replace(',', ''))
                pct = abs(float(stop_match.group(2)))
                data['stop_loss_price'] = {'price': price, 'percentage': pct}

            rr_match = re.search(r'風報比[:：]\s*1[:：]([\d.]+)', ai_text)
            if rr_match:
                data['risk_reward_ratio'] = float(rr_match.group(1))

            holding_match = re.search(r'(?:預期)?持有(?:期限)?[:：]\s*(\d+)[-~]?(\d+)?天', ai_text)
            if holding_match:
                min_days = int(holding_match.group(1))
                max_days = int(holding_match.group(2)) if holding_match.group(2) else min_days
                data['expected_holding_days'] = {'min': min_days, 'max': max_days}

            ai_text_clean = ai_text.replace('\\n', '\n')
            next_sections = r'(?=\n?倉位|\n?風險|\n?設定類型分析|\n?類型|\n?模式特徵|\n?本次評估|$)'

            reason_match = re.search(r'理由[:：]\s*(.+?)' + next_sections, ai_text_clean, re.DOTALL)
            if reason_match:
                data['key_factors'] = [reason_match.group(1).strip()]

            position_match = re.search(r'倉位[:：]\s*(.+?)' + next_sections, ai_text_clean, re.DOTALL)
            if position_match:
                data['risk_management'] = position_match.group(1).strip()

            risk_match = re.search(r'風險[:：]\s*(.+?)' + next_sections, ai_text_clean, re.DOTALL)
            if risk_match:
                data['main_risk'] = risk_match.group(1).strip()

            data['raw_text'] = ai_text_clean.strip()
            logger.info(f"Parsed {len(data)} fields from AI text")
            return data

        except Exception as e:
            logger.warning(f"Failed to parse AI text: {e}")
            return {}

    # ─── Primitive formatters ─────────────────────────────────────────────────

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

    def _fmt_obv(self, obv_trend: Optional[str]) -> str:
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


# Test
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if not TELEGRAM_AVAILABLE:
        print("Error: python-telegram-bot is not installed", file=sys.stderr)
        sys.exit(1)

    try:
        notifier = TelegramNotifier()

        test_sentiment = {
            'ai_advice_text': (
                "訊號: HOLD\n強度: 2\n信心評分: 4\n入場: N/A\n目標: N/A\n停損: N/A\n風報比: N/A\n"
                "理由: 技術指標（RSI、MACD、OBV）普遍偏空，但ETF資金流入顯示機構看多。新聞提及宏觀壓力與槓桿解除，加劇賣壓。\n"
                "倉位: 0%\n風險: 價格跌破 $68,000 情境。\n"
            ),
            'fear_greed_value': 17,
            'fear_greed_class': 'Extreme Fear',
            'institutional_summary': {
                'etf_net_m': 320,
                'lsr_ratio': 0.85,
                'funding_rate_pct': 0.01,
            },
            'news_headlines': [
                "Bitcoin faces macro headwinds as Fed holds rates",
                "Institutional ETF inflows hit weekly high",
            ],
        }

        test_signal = {
            'action': 'BUY',
            'strength': 5,
            'price': 78478,
            'atr_percent': 2.3,
            'obv_trend': 'up',
            'component_scores': {'trend': 1.2, 'momentum': 0.8, 'volume': 0.6, 'technical': 0.9},
            'indicators': {
                'rsi': 22,
                'macd': 160,
                'ema_12': 78500, 'ema_26': 77800, 'ema_50': 76000, 'ema_200': 72000,
                'adx': 28.3,
                'stoch_k': 28, 'stoch_d': 35,
                'bb_upper': 82000, 'bb_middle': 78000, 'bb_lower': 74000,
                'support': 76500, 'resistance': 81000,
            },
            'trade_plan': {
                'entries': {'conservative': 77800, 'aggressive': 78200},
                'stops': {'hard_stop': 75500},
                'targets': {'T1': 82000, 'T2': 86000, 'T3': 91000},
                'risk_reward_ratios': {'T1': 1.6, 'T2': 3.2, 'T3': 5.8},
                'position_sizing': {'recommended': 0.10, 'kelly_fraction': 0.123},
                'position_recommendation': '10%',
            },
        }

        test_signal['indicators']['volume_change'] = 45
        test_sentiment['technical_summary'] = {'rsi': 22, 'volume_change': 45}

        asyncio.run(notifier.send_signal(test_signal, test_sentiment))
        print("Test signal sent successfully!")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
