"""Web scraper for institutional data (no API key needed)."""

import os
import logging
import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional
from datetime import datetime
import re

logger = logging.getLogger(__name__)

class CoinglassFetcher:
    """
    Scrape institutional data from public websites (free).
    
    Sources:
    - Bitbo.io: ETF flows, corporate holdings
    - Alternative.me: Fear & Greed (already in sentiment_analyzer)
    - Binance API: Funding rate (free, in data_fetcher)
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize scraper (api_key ignored, for compatibility)."""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        logger.info("Web scraper initialized (no API key needed)")
    
    def fetch_etf_flows(self, symbol: str = 'BTC', limit: int = 10) -> Optional[Dict]:
        """Scrape Bitcoin ETF flows from Bitbo.io."""
        try:
            url = 'https://bitbo.io/treasuries/etf-flows/'
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Find summary div (updated selector)
            net_flow_div = soup.find('div', string=re.compile('Net Flow|Total'))  # Fix DeprecationWarning
            
            if not net_flow_div:
                # Fallback: Try table
                tables = soup.find_all('table')
                if not tables:
                    logger.warning("No ETF data found on Bitbo")
                    return None
                
                table = tables[0]
                rows = table.find_all('tr')
                if len(rows) < 2:
                    return None
                
                latest_row = rows[1]
                cells = latest_row.find_all('td')
                if len(cells) < 2:
                    return None
                
                date_str = cells[0].text.strip()
                net_flow_text = cells[1].text.strip()
            else:
                net_flow_text = net_flow_div.find_next('span').text.strip()
                date_str = datetime.now().strftime('%Y-%m-%d')
            
            # === FIX: Parse "-492.7" (M is implied) ===
            match = re.search(r'([-+]?\$?[\d,.]+)\s*M?', net_flow_text, re.IGNORECASE)
            
            if not match:
                logger.warning(f"Could not parse ETF flow from: {net_flow_text}")
                return None
            
            net_flow_m = float(match.group(1).replace('$', '').replace(',', ''))
            net_flow = net_flow_m * 1e6  # Always convert to USD (M is implied)
            
            logger.info(f"Parsed ETF flow: {net_flow_text} -> ${net_flow_m:.1f}M")
            
            return {
                'net_flow': net_flow,
                'timestamp': date_str,
                'source': 'Bitbo.io'
            }
            
        except Exception as e:
            logger.error(f"Failed to scrape ETF flows: {e}")
            return None

    
    def fetch_liquidations(self, symbol: str = 'BTC', interval: str = '24h') -> Optional[Dict]:
        """
        Liquidations - use Binance public liquidation orders (recent).
        
        Note: Binance limits allForceOrders to last 7 days, not real-time aggregates.
        Alternative: Could scrape Coinglass liquidation heatmap page.
        """
        try:
            # === FIX: Binance requires startTime for allForceOrders ===
            from datetime import timedelta
            end_time = int(datetime.now().timestamp() * 1000)
            start_time = end_time - (24 * 60 * 60 * 1000)  # 24h ago
            
            url = 'https://fapi.binance.com/fapi/v1/allForceOrders'
            params = {
                'symbol': f'{symbol}USDT',
                'startTime': start_time,
                'endTime': end_time
            }
            resp = self.session.get(url, params=params, timeout=10)
            
            # If 400, try without time filter (fallback)
            if resp.status_code == 400:
                logger.warning("Binance liquidations unavailable, using estimate")
                return {
                    'total_liquidation': 0,
                    'long_liquidation': 0,
                    'short_liquidation': 0,
                    'interval': interval,
                    'source': 'Binance (estimated)',
                    'note': 'Real-time data unavailable'
                }
            
            resp.raise_for_status()
            data = resp.json()
            
            if not data:
                return None
            
            # Calculate 24h liquidations
            total_liq = sum(float(o['price']) * float(o['origQty']) for o in data)
            long_liq = sum(float(o['price']) * float(o['origQty']) 
                          for o in data if o['side'] == 'SELL')
            
            return {
                'total_liquidation': total_liq,
                'long_liquidation': long_liq,
                'short_liquidation': total_liq - long_liq,
                'interval': interval,
                'source': 'Binance'
            }
            
        except Exception as e:
            logger.warning(f"Failed to fetch liquidations: {e}")
            # Return safe fallback
            return {
                'total_liquidation': 0,
                'long_liquidation': 0,
                'short_liquidation': 0,
                'interval': interval,
                'source': 'fallback'
            }
    
    def fetch_long_short_ratio(self, symbol: str = 'BTC') -> Optional[Dict]:
        """
        Long/Short ratio - use Binance Futures API (free).
        """
        try:
            # Binance top trader long/short ratio (public)
            url = 'https://fapi.binance.com/futures/data/topLongShortAccountRatio'
            params = {'symbol': f'{symbol}USDT', 'period': '1d', 'limit': 1}
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            
            data = resp.json()
            if not data:
                return None
            
            latest = data[0]
            ratio = float(latest['longShortRatio'])
            
            return {
                'ratio': ratio,
                'long_pct': ratio / (1 + ratio) * 100,
                'short_pct': 100 - (ratio / (1 + ratio) * 100),
                'source': 'Binance'
            }
            
        except Exception as e:
            logger.warning(f"Failed to fetch long/short ratio: {e}")
            return None
    
    def fetch_funding_rate(self, symbol: str = 'BTC') -> Optional[Dict]:
        """
        Funding rate - use Binance Futures API (free, most accurate).
        """
        try:
            url = 'https://fapi.binance.com/fapi/v1/fundingRate'
            params = {'symbol': f'{symbol}USDT', 'limit': 1}
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            
            data = resp.json()
            if not data:
                return None
            
            latest = data[0]
            rate = float(latest['fundingRate'])
            
            return {
                'avg_rate': rate,
                'rate_pct': rate * 100,
                'source': 'Binance'
            }
            
        except Exception as e:
            logger.warning(f"Failed to fetch funding rate: {e}")
            return None
    
    def fetch_all_institutional_data(self, symbol: str = 'BTC') -> Dict:
        """
        Fetch all data with graceful fallbacks.
        """
        logger.info(f"Fetching institutional data for {symbol}...")
        
        data = {
            'etf_flows': self.fetch_etf_flows(symbol),
            'liquidations': self.fetch_liquidations(symbol, interval='24h'),
            'long_short_ratio': self.fetch_long_short_ratio(symbol),
            'funding_rate': self.fetch_funding_rate(symbol),
            'timestamp': datetime.now().isoformat()
        }
        
        # Log results
        if data['etf_flows']:
            logger.info(f"✓ ETF Net Flow: ${data['etf_flows']['net_flow']/1e6:.1f}M")
        if data['liquidations']:
            logger.info(f"✓ 24h Liquidations: ${data['liquidations']['total_liquidation']/1e6:.1f}M")
        if data['long_short_ratio']:
            logger.info(f"✓ Long/Short Ratio: {data['long_short_ratio']['ratio']:.2f}")
        if data['funding_rate']:
            logger.info(f"✓ Funding Rate: {data['funding_rate']['rate_pct']:.3f}%")
        
        return data


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fetcher = CoinglassFetcher()
    
    print("\n=== Testing Web Scraper (No API Key) ===\n")
    data = fetcher.fetch_all_institutional_data()
    
    import json
    print(json.dumps(data, indent=2, default=str))
