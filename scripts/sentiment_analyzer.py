"""Sentiment analysis module using external data sources and Gemini AI."""
import requests
import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from pathlib import Path
import sys
import pandas as pd

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Use google-generativeai directly (simpler, fewer conflicts)
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logging.warning("google-generativeai not available")

from scripts.utils import load_config

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """
    Analyzes market sentiment using multiple data sources:
    - Fear & Greed Index (Alternative.me)
    - CryptoCompare News API
    - Gemini AI for synthesis
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize sentiment analyzer."""
        self.config = load_config(config_path)
        
        # Initialize Gemini model (using google-generativeai directly)
        self.model = None
        if GENAI_AVAILABLE:
            try:
                gemini_key = self.config['api_keys'].get('gemini_api_key', '')
                if gemini_key and gemini_key != "YOUR_GEMINI_API_KEY":
                    genai.configure(api_key=gemini_key)
                    self.model = genai.GenerativeModel(
                        model_name="gemini-2.5-flash-lite",
                        generation_config={
                            "temperature": 0.3,
                            "max_output_tokens": 2048,
                            "top_p": 0.95,
                            "top_k": 40
                        }
                    )
                    logger.info("Sentiment analyzer initialized with Gemini 2.5 Flash Lite")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini: {e}")
    
    def fetch_fear_greed_index(self) -> Dict:
        """
        Fetch Fear & Greed Index from Alternative.me API.
        
        Returns:
            Dictionary with index value, classification, and timestamp
        """
        try:
            url = "https://api.alternative.me/fng/?limit=7"  # Last 7 days
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'data' not in data or not data['data']:
                raise ValueError("No Fear & Greed data available")
            
            current = data['data'][0]
            history = data['data'][:7]
            
            # Calculate trend
            values = [int(d['value']) for d in history]
            trend = "上升" if values[0] > values[-1] else "下降" if values[0] < values[-1] else "持平"
            avg_7d = sum(values) / len(values)
            
            result = {
                'value': int(current['value']),
                'classification': current['value_classification'],
                'timestamp': current['timestamp'],
                'trend_7d': trend,
                'avg_7d': avg_7d,
                'history': values
            }
            
            logger.info(f"Fear & Greed Index: {result['value']} ({result['classification']})")
            return result
            
        except Exception as e:
            logger.warning(f"Failed to fetch Fear & Greed Index: {e}")
            return {
                'value': 50,
                'classification': 'Neutral',
                'trend_7d': '未知',
                'avg_7d': 50,
                'history': [],
                'error': str(e)
            }
    
    def analyze_sentiment_with_ai(
        self,
        fear_greed: Dict,
        news: List[Dict],
        df_with_indicators: pd.DataFrame,
        current_price: float,
        institutional_data: Dict
    ) -> Dict:
        """
        Use Gemini AI to synthesize all data into actionable sentiment analysis.
        
        Args:
            fear_greed: Fear & Greed Index data
            news: List of news articles
            df_with_indicators: DataFrame with calculated technical indicators
            current_price: Current BTCUSDT price
            institutional_data: Institutional data
        Returns:
            Dictionary with AI sentiment analysis
        """
        try: 
            latest = df_with_indicators.iloc[-1]
            
            # Extract indicators from DataFrame
            tech_rsi = float(latest['rsi']) if pd.notna(latest.get('rsi')) else 50
            tech_macd = float(latest['macd']) if pd.notna(latest.get('macd')) else 0
            tech_ema12 = float(latest['ema_12']) if pd.notna(latest.get('ema_12')) else 0
            tech_bb_upper = float(latest['bb_upper']) if pd.notna(latest.get('bb_upper')) else None
            tech_bb_middle = float(latest['bb_middle']) if pd.notna(latest.get('bb_middle')) else None
            tech_bb_lower = float(latest['bb_lower']) if pd.notna(latest.get('bb_lower')) else None
            tech_obv = float(latest['obv']) if pd.notna(latest.get('obv')) else None
            tech_volume_change = float(latest['volume_change']) if pd.notna(latest.get('volume_change')) else 0.0
            
            # Clamp volume change to reasonable range (-100% to +1000%)
            if tech_volume_change < -100:
                tech_volume_change = -100
            elif tech_volume_change > 1000:
                tech_volume_change = 1000
            
            # Calculate OBV trend (direction and magnitude over recent period)
            obv_change_pct = None
            if tech_obv is not None and len(df_with_indicators) >= 7:
                # Compare current OBV with OBV from 7 periods ago for more stable trend
                obv_7_periods_ago = float(df_with_indicators.iloc[-7]['obv']) if pd.notna(df_with_indicators.iloc[-7].get('obv')) else None
                if obv_7_periods_ago is not None and abs(obv_7_periods_ago) > 0:
                    # Calculate percentage change over 7 periods
                    obv_change_pct = ((tech_obv - obv_7_periods_ago) / abs(obv_7_periods_ago)) * 100
                    # Clamp to reasonable range (-50% to +50%)
                    if obv_change_pct < -50:
                        obv_change_pct = -50
                    elif obv_change_pct > 50:
                        obv_change_pct = 50
            
            fear_greed_value = fear_greed.get('value', 50)
            fear_greed_class = fear_greed.get('classification', 'Neutral')
            
            # EMA12 difference percentage
            ema_diff_pct = 0.0
            if tech_ema12 is not None and current_price > 0:
                ema_diff_pct = ((current_price - tech_ema12) / tech_ema12) * 100
            
            # Bollinger Bands position (0-1, where 0=lower, 0.5=middle, 1=upper)
            bb_position = 0.5
            if tech_bb_upper is not None and tech_bb_lower is not None and current_price > 0:
                bb_range = tech_bb_upper - tech_bb_lower
                if bb_range > 0:
                    bb_position = (current_price - tech_bb_lower) / bb_range
                    # Clamp to valid range [0, 1]
                    bb_position = max(0.0, min(1.0, bb_position))
            
            # Format BB position as percentage (0-100%)
            bb_position_pct = bb_position * 100
            
            # Format OBV and Volume for prompt
            obv_str = f"{obv_change_pct:+.1f}%" if obv_change_pct is not None else "N/A"
            vol_str = f"{tech_volume_change:+.1f}%"

            institutional_prompt = ""
            etf_net = None
            liq_total = None
            lsr_ratio = None
            if institutional_data:
                try:
                    etf_net = institutional_data.get('etf_flows', {}).get('net_flow', 0) / 1e6
                    liq_total = institutional_data.get('liquidations', {}).get('total_liquidation', 0) / 1e6
                    lsr_ratio = institutional_data.get('long_short_ratio', {}).get('ratio', 1.0)
                    funding_pct = institutional_data.get('funding_rate', {}).get('rate_pct', 0)
                    
                    etf_signal = "bullish" if etf_net > 50 else "bearish" if etf_net < -50 else "neutral"
                    lsr_signal = "shorts" if lsr_ratio < 0.9 else "longs" if lsr_ratio > 1.1 else "balanced"
                    funding_signal = "overheat" if funding_pct > 0.1 else "oversold" if funding_pct < -0.05 else "neutral"

                    institutional_prompt = f"""
                    Inst Data:
                    ETF:${etf_net:.0f}M({etf_signal}) Liq:${liq_total:.0f}M L/S:{lsr_ratio:.2f}({lsr_signal}) FR:{funding_pct:.3f}%({funding_signal})
                    """
                except Exception as e:
                    logger.warning(f"⚠ Failed to format institutional data: {e}")
                    institutional_prompt = ""
            

            news_context = ""
            if news and len(news) > 0:
                headlines = [article['title'] for article in news[:3]]
                news_context = f"Recent News: {' | '.join(headlines)}"
            # Updated prompt with new format
            prompt = f"""You are a professional crypto quant analyst who combines technical indicators, sentiment, and news to make risk-controlled trading decisions.
BTCUSDT ${current_price:,.0f} Fear&Greed:{fear_greed_value} RSI:{tech_rsi:.0f} MACD:{tech_macd:+.0f} EMA diff:{ema_diff_pct:+.1f}% BB:{bb_position_pct:.0f}% OBV:{obv_str} Vol:{vol_str}
{institutional_prompt}
{news_context}
Analysis instructions: Analyze the data objectively. Acknowledge when signals conflict. If conviction is low (<5), recommend HOLD instead of forcing a trade. Be honest about uncertainty - it's better than false confidence.
Output format (exact):
訊號: BUY/SELL/HOLD
強度: 1-5(1=不建議交易 2=次佳設定，訊號不清 3=標準設定，可接受 4=良好設定，多指標支持 5=優質設定，罕見機會)
信心評分: 1-10(1-2=訊號矛盾/數據不足 3-4=低確定性，衝突多 5-6=中等確定性 7-8=高確定性，多指標一致 9-10=極端罕見且明確)
入場: $低點 - $高點 (分批進場區間)
目標: 價格 (+漲幅%)
停損: 價格 (-跌幅%)
風報比: 1:X.X
理由: 技術+情緒+機構+新聞各1點，120字內
倉位: 建議總資金%+分批策略
風險: 若跌破$XX,XXX則停損離場；若[具體事件]發生則重新評估
設定類型分析:
類型: [極度超賣反彈/趨勢突破/盤整震盪/反轉訊號/無明確設定]
模式特徵: [此類設定的3個關鍵特徵]
典型表現: 
- 平均持有: X-Y天
- 常見回撤: -X%
- 最佳進場時機: [具體描述]
- 常見失敗原因: [1-2個陷阱]
本次評估:
- 與典型案例相比: [更強/相當/較弱]
- 特殊風險: [本次獨特風險點]
直接輸出，不要JSON。
            """
            logger.info(f"Prompt message: {prompt}")
            # Use google-generativeai directly
            response = self.model.generate_content(prompt)

            if hasattr(response, 'usage_metadata'):
                logger.info(f"Prompt tokens: {response.usage_metadata.prompt_token_count}")
                logger.info(f"Candidates tokens: {response.usage_metadata.candidates_token_count}")
                logger.info(f"Total tokens: {response.usage_metadata.total_token_count}")
            
            logger.info(f"Google finish reason: {response.candidates[0].finish_reason}")
            ai_text = response.text
            
            # Return simple structure with AI advice text only
            result = {
                'ai_generated': True,
                'ai_advice_text': ai_text,  # Store cleaned AI output for Telegram
                'fear_greed_value': fear_greed_value,
                'fear_greed_class': fear_greed_class,
                'institutional_summary': {
                    'etf_net_m': etf_net if institutional_data else None,
                    'liq_total_m': liq_total if institutional_data else None,
                    'lsr_ratio': lsr_ratio if institutional_data else None
                } if institutional_data else None
            }
            
            logger.info(f"AI Sentiment analysis completed (Fear & Greed: {result['fear_greed_value']})")
            
            return result
            
        except Exception as e:
            logger.warning(f"AI sentiment analysis failed: {e}")
            return self._generate_template_sentiment(fear_greed, df_with_indicators)
    
    
    def _generate_template_sentiment(self, fear_greed: Dict, df_with_indicators: pd.DataFrame) -> Dict:
        """Generate template-based sentiment when AI is unavailable."""
        fg_value = fear_greed.get('value', 50)
        
        # Determine action from RSI (simple fallback)
        tech_action = 'HOLD'
        if len(df_with_indicators) > 0:
            latest = df_with_indicators.iloc[-1]
            rsi = latest.get('rsi') if pd.notna(latest.get('rsi')) else None
            if rsi is not None:
                if rsi < 30:
                    tech_action = 'BUY'
                elif rsi > 70:
                    tech_action = 'SELL'
        
        # Determine sentiment class from Fear & Greed
        if fg_value <= 20:
            sentiment_class = '極度恐懼'
            sentiment_score = 2
        elif fg_value <= 40:
            sentiment_class = '恐懼'
            sentiment_score = 4
        elif fg_value <= 60:
            sentiment_class = '中性'
            sentiment_score = 5
        elif fg_value <= 80:
            sentiment_class = '貪婪'
            sentiment_score = 7
        else:
            sentiment_class = '極度貪婪'
            sentiment_score = 9
        
        # Determine consistency
        if (fg_value < 40 and tech_action == 'BUY') or (fg_value > 60 and tech_action == 'SELL'):
            consistency = '存在分歧'
            recommendation = '持有觀望'
        elif fg_value < 40 and tech_action == 'SELL':
            consistency = '一致看空'
            recommendation = '逢高減倉'
        elif fg_value > 60 and tech_action == 'BUY':
            consistency = '一致看多'
            recommendation = '分批建倉'
        else:
            consistency = '不明確'
            recommendation = '持有觀望'
        
        # Generate template-based advice text for Telegram
        template_advice = self._generate_template_advice(tech_action, fg_value, recommendation)
        
        return {
            'sentiment_score': sentiment_score,
            'sentiment_class': sentiment_class,
            'consistency': consistency,
            'recommendation': recommendation,
            'risk_warning': f"恐懼貪婪指數 {fg_value}，市場情緒{sentiment_class}，注意風險",
            'key_observation': f"技術面{tech_action}，情緒面{sentiment_class}",
            'raw_analysis': None,
            'fear_greed_value': fg_value,
            'fear_greed_class': fear_greed.get('classification', 'Neutral'),
            'ai_generated': False,  # Flag: template used, not AI
            'ai_advice_text': template_advice  # Fallback advice text
        }
    
    def _generate_template_advice(self, tech_action: str, fear_greed: int, recommendation: str) -> str:
        """Generate template-based advice when Gemini is unavailable."""
        if recommendation == '積極買入' or (tech_action == 'BUY' and fear_greed < 30):
            return "交易訊號: 分批建倉\n• RSI超賣區，恐懼指數偏低\n風險管理: 若進場建議分2-3批，首批30%倉位\n主要風險: 若跌破支撐位需及時停損"
        elif recommendation == '分批建倉' or tech_action == 'BUY':
            return "交易訊號: 分批建倉\n• 技術面偏多，注意倉位控制\n風險管理: 若進場建議輕倉20-30%\n主要風險: 若跌破前低需重新評估"
        elif recommendation == '逢高減倉' or tech_action == 'SELL':
            return "交易訊號: 逢高減倉\n• 技術面偏空，建議減少持倉\n風險管理: 若持有部位可減倉30-50%\n主要風險: 若續跌可能加速下行"
        elif recommendation == '立即止損':
            return "交易訊號: 立即止損\n• 多重風險訊號，建議離場\n風險管理: 減倉50-70%，保留觀察倉位\n主要風險: 若不及時止損可能擴大損失"
        else:  # 持有觀望
            return "交易訊號: 持有觀望\n• 訊號不明確，建議等待\n風險管理: 暫不建議新開倉位\n主要風險: 方向不明時進場容易兩面挨打"
    


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    analyzer = SentimentAnalyzer()
    
    # Mock technical signal for testing
    mock_signal = {
        'action': 'HOLD',
        'strength': 2,
        'indicators': {
            'rsi': 55,
            'price_change_24h': -1.5
        }
    }
    
    sentiment = analyzer.get_full_sentiment_analysis(mock_signal)
    
    print("\n=== Sentiment Analysis Results ===")
    print(f"Score: {sentiment['sentiment_score']}/10")
    print(f"Class: {sentiment['sentiment_class']}")
    print(f"Fear & Greed: {sentiment['fear_greed_value']} ({sentiment['fear_greed_class']})")
    print(f"Consistency: {sentiment['consistency']}")
    print(f"Recommendation: {sentiment['recommendation']}")
    print(f"Risk: {sentiment['risk_warning']}")
    print(f"Key Observation: {sentiment['key_observation']}")
    if sentiment.get('news_headlines'):
        print(f"\nTop Headlines:")
        for headline in sentiment['news_headlines']:
            print(f"  • {headline[:60]}...")

