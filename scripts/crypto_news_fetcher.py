"""Crypto news fetcher using CryptoCompare API."""
import requests
from typing import List, Dict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class CryptoNewsFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        logger.info("Crypto news fetcher initialized")

    def fetch_crypto_news(self, limit: int = 5) -> List[Dict]:
        """
        Fetch recent crypto news from CryptoCompare API (free tier).
        
        Args:
            limit: Number of news articles to fetch
            
        Returns:
            List of news articles with title, source, and sentiment hints
        """
        try:
            # CryptoCompare News API (free, no key needed for basic)
            url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN&categories=BTC&excludeCategories=Sponsored"
            
            # FIX: Use self.session instead of requests
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'Data' not in data:
                raise ValueError("No news data available")
            
            articles = []
            for article in data['Data'][:limit]:
                articles.append({
                    'title': article.get('title', ''),
                    'body': article.get('body', ''),
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


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fetcher = CryptoNewsFetcher()
    
    print("\n=== Testing Crypto news fetcher ===\n")
    data = fetcher.fetch_crypto_news()
    
    import json
    print(json.dumps(data, indent=2, default=str))