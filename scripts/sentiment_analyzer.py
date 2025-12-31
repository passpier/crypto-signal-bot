"""Sentiment analysis module using external data sources and Gemini AI."""
import requests
import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from pathlib import Path
import sys

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
                        model_name="gemini-2.5-flash",  # Latest stable, separate quota
                        generation_config={
                            "temperature": 0.3,
                            "max_output_tokens": 1000,  # Increased for detailed trading plans
                        }
                    )
                    logger.info("Sentiment analyzer initialized with Gemini 2.5 Flash")
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
    
    def fetch_crypto_news(self, limit: int = 10) -> List[Dict]:
        """
        Fetch recent crypto news from CryptoCompare API (free tier).
        
        Args:
            limit: Number of news articles to fetch
            
        Returns:
            List of news articles with title, source, and sentiment hints
        """
        try:
            # CryptoCompare News API (free, no key needed for basic)
            url = f"https://min-api.cryptocompare.com/data/v2/news/?lang=EN&categories=BTC&excludeCategories=Sponsored"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'Data' not in data:
                raise ValueError("No news data available")
            
            articles = []
            for article in data['Data'][:limit]:
                articles.append({
                    'title': article.get('title', ''),
                    'source': article.get('source', ''),
                    'published': datetime.fromtimestamp(article.get('published_on', 0)).strftime('%Y-%m-%d %H:%M'),
                    'url': article.get('url', ''),
                    'categories': article.get('categories', '')
                })
            
            logger.info(f"Fetched {len(articles)} news articles")
            return articles
            
        except Exception as e:
            logger.warning(f"Failed to fetch crypto news: {e}")
            return []
    
    def fetch_market_data_summary(self) -> Dict:
        """
        Fetch additional market data from CoinGecko (free API).
        
        Returns:
            Dictionary with market cap, dominance, and volume data
        """
        try:
            # Global market data
            url = "https://api.coingecko.com/api/v3/global"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()['data']
            
            result = {
                'total_market_cap_usd': data['total_market_cap']['usd'],
                'total_volume_24h': data['total_volume']['usd'],
                'btc_dominance': data['market_cap_percentage']['btc'],
                'market_cap_change_24h': data['market_cap_change_percentage_24h_usd'],
                'active_cryptocurrencies': data['active_cryptocurrencies']
            }
            
            logger.info(f"BTC Dominance: {result['btc_dominance']:.1f}%")
            return result
            
        except Exception as e:
            logger.warning(f"Failed to fetch market data: {e}")
            return {
                'btc_dominance': 0,
                'market_cap_change_24h': 0,
                'error': str(e)
            }
    
    def analyze_sentiment_with_ai(
        self,
        fear_greed: Dict,
        news: List[Dict],
        market_data: Dict,
        technical_signal: Dict
    ) -> Dict:
        """
        Use Gemini AI to synthesize all data into actionable sentiment analysis.
        
        Args:
            fear_greed: Fear & Greed Index data
            news: List of news articles
            market_data: Market overview data
            technical_signal: Technical analysis results
            
        Returns:
            Dictionary with AI sentiment analysis
        """
        if not self.model:
            return self._generate_template_sentiment(fear_greed, technical_signal)
        
        try:
            # Build simplified prompt for direct Telegram output
            action_zh = {'BUY': '買入', 'SELL': '賣出', 'HOLD': '觀望'}.get(
                technical_signal.get('action', 'HOLD'), '觀望'
            )
            rsi = technical_signal.get('indicators', {}).get('rsi', 50)
            strength = technical_signal.get('strength', 3)
            price_change = technical_signal.get('indicators', {}).get('price_change_24h', 0)
            
            # Safe access to nested dictionaries
            btc_dominance = market_data.get('btc_dominance', 0)
            tech_action = technical_signal.get('action', 'HOLD')
            tech_strength = technical_signal.get('strength', 3)
            indicators = technical_signal.get('indicators', {})
            tech_rsi = indicators.get('rsi', 50)
            tech_price_change = indicators.get('price_change_24h', 0)
            
            fear_greed_value = fear_greed.get('value', 50)
            fear_greed_class = fear_greed.get('classification', 'Neutral')
            
            # Add contrarian context to prompt
            contrarian_note = ""
            if fear_greed_value <= 25 and tech_action == 'HOLD':
                contrarian_note = "\n重要：極度恐懼(≤25)配合中性技術面，可能是 contrarian 買入機會。"
            elif fear_greed_value >= 75 and tech_action == 'HOLD':
                contrarian_note = "\n重要：極度貪婪(≥75)配合中性技術面，可能是 contrarian 賣出機會。"
            
            # Simplified prompt to avoid truncation - use concise format that works
            prompt = f"""BTC市場數據：恐懼指數{fear_greed_value}({fear_greed_class})，RSI={tech_rsi}，技術訊號{tech_action}(強度{tech_strength}/5)，24h變化{tech_price_change:+.1f}%。
{contrarian_note}

請用繁體中文給出100字內的交易分析，包含：
1. 交易建議（買入/賣出/觀望）
2. 關鍵因素（2個）
3. 倉位建議（分幾批進場，每批多少%）
4. 主要風險（一句話）

純文字輸出，不要markdown符號，不要免責聲明。"""
            
            # Use google-generativeai directly
            response = self.model.generate_content(prompt)
            
            # Check if response was truncated
            finish_reason = response.candidates[0].finish_reason if response.candidates else None
            if finish_reason == 2:  # MAX_TOKENS - response was truncated
                logger.warning(f"Gemini response truncated (finish_reason: {finish_reason}). Response may be incomplete.")
                # Try to get partial response
                if response.candidates and response.candidates[0].content:
                    ai_text = response.candidates[0].content.parts[0].text if response.candidates[0].content.parts else response.text
                else:
                    ai_text = response.text
            else:
                ai_text = response.text
            
            # Clean any markdown that might slip through
            import re
            # Remove markdown formatting more thoroughly
            ai_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', ai_text)  # Bold
            ai_text = re.sub(r'\*([^*]+)\*', r'\1', ai_text)  # Italic
            ai_text = re.sub(r'`([^`]+)`', r'\1', ai_text)  # Code blocks
            ai_text = re.sub(r'#{1,6}\s+', '', ai_text)  # Headers
            ai_text = re.sub(r'^\s*[-*+]\s+', '', ai_text, flags=re.MULTILINE)  # List markers at start of line
            ai_text = re.sub(r'\n{3,}', '\n\n', ai_text)  # Multiple newlines
            ai_text = ai_text.strip()
            
            # Parse AI response and store cleaned output for Telegram
            parsed = self._parse_ai_response(ai_text, fear_greed)
            parsed['ai_generated'] = True  # Flag to indicate AI was used
            parsed['ai_advice_text'] = ai_text  # Store cleaned AI output for Telegram
            logger.info(f"AI Sentiment: {parsed['sentiment_class']} (Score: {parsed['sentiment_score']})")
            
            return parsed
            
        except Exception as e:
            logger.warning(f"AI sentiment analysis failed: {e}")
            return self._generate_template_sentiment(fear_greed, technical_signal)
    
    def _parse_ai_response(self, ai_text: str, fear_greed: Dict) -> Dict:
        """Parse AI response into structured data."""
        lines = ai_text.strip().split('\n')
        
        result = {
            'sentiment_score': 5,
            'sentiment_class': '中性',
            'consistency': '不明確',
            'recommendation': '持有觀望',
            'risk_warning': '市場波動大，注意風險控制',
            'key_observation': '關注市場動向',
            'raw_analysis': ai_text,
            'fear_greed_value': fear_greed['value'],
            'fear_greed_class': fear_greed['classification']
        }
        
        for line in lines:
            line = line.strip()
            if '市場情緒評分' in line or '情緒評分' in line:
                try:
                    # Extract number from line
                    import re
                    numbers = re.findall(r'\d+', line)
                    if numbers:
                        result['sentiment_score'] = min(int(numbers[0]), 10)
                except:
                    pass
            elif '情緒分類' in line:
                for cls in ['極度恐懼', '恐懼', '中性', '貪婪', '極度貪婪']:
                    if cls in line:
                        result['sentiment_class'] = cls
                        break
            elif '一致性' in line:
                for cons in ['一致看多', '一致看空', '存在分歧', '不明確']:
                    if cons in line:
                        result['consistency'] = cons
                        break
            elif '綜合建議' in line:
                for rec in ['積極買入', '分批建倉', '持有觀望', '逢高減倉', '立即止損']:
                    if rec in line:
                        result['recommendation'] = rec
                        break
            elif '風險提示' in line:
                parts = line.split(':', 1)
                if len(parts) > 1:
                    result['risk_warning'] = parts[1].strip()[:100]
            elif '關鍵觀察' in line:
                parts = line.split(':', 1)
                if len(parts) > 1:
                    result['key_observation'] = parts[1].strip()[:50]
        
        return result
    
    def _generate_template_sentiment(self, fear_greed: Dict, technical_signal: Dict) -> Dict:
        """Generate template-based sentiment when AI is unavailable."""
        fg_value = fear_greed.get('value', 50)
        tech_action = technical_signal.get('action', 'HOLD')
        
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
    
    def get_full_sentiment_analysis(self, technical_signal: Dict) -> Dict:
        """
        Get complete sentiment analysis combining all data sources.
        
        Args:
            technical_signal: Technical analysis results from signal_generator
            
        Returns:
            Complete sentiment analysis dictionary
        """
        logger.info("Starting sentiment analysis...")
        
        # Fetch all data sources
        fear_greed = self.fetch_fear_greed_index()
        news = self.fetch_crypto_news(limit=5)
        market_data = self.fetch_market_data_summary()
        
        # AI synthesis
        sentiment = self.analyze_sentiment_with_ai(
            fear_greed=fear_greed,
            news=news,
            market_data=market_data,
            technical_signal=technical_signal
        )
        
        # Add raw data to result
        sentiment['news_headlines'] = [n['title'] for n in news[:3]]
        sentiment['market_data'] = {
            'btc_dominance': market_data.get('btc_dominance', 0),
            'market_cap_change': market_data.get('market_cap_change_24h', 0)
        }
        
        return sentiment


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

