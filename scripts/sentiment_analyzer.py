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
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logging.warning("google-genai not available")

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
        self.client = None
        self.model_name = None
        self.generation_config = None
        if GENAI_AVAILABLE:
            try:
                gemini_key = (self.config.get('api_keys') or {}).get('gemini_api_key', '') or ''
                gemini_key = (gemini_key or '').strip()
                if not gemini_key or gemini_key == "YOUR_GEMINI_API_KEY":
                    logger.info(
                        "GEMINI_API_KEY not set or still placeholder (len=%s); AI sentiment will use template.",
                        len(gemini_key) if gemini_key else 0,
                    )
                else:
                    self.client = genai.Client(api_key=gemini_key)
                    # Prefer 2.5 Flash Lite; fallback to 2.0 Flash if needed
                    self.model_name = "gemini-2.5-flash-lite"
                    self.generation_config = genai.types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=5000,
                        top_p=0.95,
                        top_k=40,
                    )
                    logger.info(
                        "Sentiment analyzer initialized with Gemini (model=%s, key length=%d)",
                        self.model_name,
                        len(gemini_key),
                    )
            except Exception as e:
                logger.warning("Failed to initialize Gemini: %s", e, exc_info=True)
    
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
        institutional_data: Dict,
        tech_signal: Optional[Dict] = None
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
            data_warnings = []
            missing = []
            etf_net = None
            lsr_ratio = None
            if not institutional_data:
                missing = ['ETF flows', 'Long/Short Ratio', 'Funding Rate']
                warning_text = "機構即時數據缺失: " + ", ".join(missing)
                data_warnings.append(warning_text)
                logger.warning(warning_text)
            if institutional_data:
                try:
                    realtime_status = institutional_data.get('realtime_status', {}) if isinstance(institutional_data, dict) else {}
                    missing = realtime_status.get('missing', []) if isinstance(realtime_status, dict) else []
                    if missing:
                        warning_text = f"機構即時數據缺失: {', '.join(missing)}"
                        data_warnings.append(warning_text)
                        logger.warning(warning_text)

                    etf_net = institutional_data.get('etf_flows', {}).get('net_flow', 0) / 1e6
                    lsr_ratio = institutional_data.get('long_short_ratio', {}).get('ratio', 1.0)
                    funding_pct = institutional_data.get('funding_rate', {}).get('rate_pct', 0)
                    
                    etf_signal = "bullish" if etf_net > 50 else "bearish" if etf_net < -50 else "neutral"
                    lsr_signal = "shorts" if lsr_ratio < 0.9 else "longs" if lsr_ratio > 1.1 else "balanced"
                    funding_signal = "overheat" if funding_pct > 0.1 else "oversold" if funding_pct < -0.05 else "neutral"

                    warnings_line = f"\nData Warning: {data_warnings[0]}" if data_warnings else ""
                    institutional_prompt = f"""
Inst Data:
ETF:${etf_net:.0f}M({etf_signal}) L/S:{lsr_ratio:.2f}({lsr_signal}) FR:{funding_pct:.3f}%({funding_signal}){warnings_line}
                    """
                except Exception as e:
                    logger.warning(f"⚠ Failed to format institutional data: {e}")
                    institutional_prompt = ""
            

            news_context = ""
            if news and len(news) > 0:
                news_items = []
                for article in news[:3]:
                    title = article.get('title', 'No Title')
                    body = article.get('body', 'No Body')[:1000]
                    published = article.get('published', 'Unknown Time')
                    news_items.append(f"Title: {title}\nTime: {published}\nContent: {body}\n---")
                news_context = "Recent News:\n" + "\n".join(news_items)
            tech_signal_action = tech_signal.get('action') if tech_signal else "N/A"
            tech_signal_strength = tech_signal.get('strength') if tech_signal else "N/A"
            tech_signal_score = tech_signal.get('score') if tech_signal else "N/A"

            prompt = f"""You are a professional crypto quant analyst who combines technical indicators, sentiment, and news to make risk-controlled trading decisions.

=== Market Data ===
BTCUSDT ${current_price:,.0f}
Technical: RSI:{tech_rsi:.0f} MACD:{tech_macd:+.0f} EMA12 diff%:{ema_diff_pct:+.1f}% BB position:{bb_position_pct:.0f}% OBV change:{obv_str} Volume change (7d avg):{vol_str}
Computed Technical Signal: {tech_signal_action} | Strength:{tech_signal_strength}/5 | Score:{tech_signal_score}
Fear&Greed:{fear_greed_value} (Class:{fear_greed_class})
{institutional_prompt}
{news_context}

=== Rules ===
Analysis instructions: Analyze Bitcoin (BTC) investment opportunity objectively. 
Acknowledge when signals conflict. Never fabricate levels, targets, percentages, 
or ratios. If a required value cannot be justified, output "N/A". If data is 
insufficient or conviction is low, recommend HOLD instead of forcing a trade.

== Output format(exact) ==
分類：極度超賣反彈/趨勢突破/盤整震盪/反轉/無明確
訊號: BUY/SELL/HOLD
理由: 技術面／情緒面／機構面／新聞面各1點，並總結，200字內
            """
            logger.info(f"Prompt message: {prompt}")
            if self.client is None:
                logger.warning("Gemini client not initialized (missing or invalid API key); using template sentiment")
                return self._generate_template_sentiment(fear_greed, df_with_indicators)
            # Use google-genai; retry with fallback model if primary is unavailable
            model_to_try = self.model_name
            for attempt in range(2):
                try:
                    response = self.client.models.generate_content(
                        model=model_to_try,
                        contents=prompt,
                        config=self.generation_config,
                    )
                    break
                except Exception as e:
                    if attempt == 0 and model_to_try == "gemini-2.5-flash-lite":
                        model_to_try = "gemini-2.0-flash"
                        logger.info("Retrying with fallback model: %s (error: %s)", model_to_try, e)
                    else:
                        raise

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
                'data_warnings': data_warnings,
                'institutional_missing': missing if institutional_data else [],
                'institutional_summary': {
                    'etf_net_m': etf_net if institutional_data else None,
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
        
        # Non-technical fallback does not infer trading action from indicators
        tech_action = 'HOLD'
        
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
        """Generate template-based advice when Gemini is unavailable (composite, with tech verification)."""
        sentiment_note = "市場情緒偏恐懼，資金與情緒可能反覆" if fear_greed < 40 else \
                         "市場情緒偏貪婪，短線可能波動放大" if fear_greed > 60 else \
                         "市場情緒中性，缺乏明確情緒方向"
        return (
            "信心評分: 5\n"
            f"理由: 技術面以量化訊號作驗證；情緒面中性；機構面缺乏明確資金方向；新聞面缺乏重大催化。{sentiment_note}\n"
            "倉位: 風險偏好中性 + 分批進場（以時間分散為主）\n"
            "風險: 政策/監管變動可能壓低信心；流動性驟降會放大波動\n"
            "本次評估:\n- 特殊風險: 非技術面訊號不足\n"
        )
    


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
