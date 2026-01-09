"""Data fetching module for cryptocurrency price data."""
import requests
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import pandas as pd
import logging
from time import sleep
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.utils import get_project_root, IS_AZURE_FUNCTIONS

logger = logging.getLogger(__name__)


class CryptoDataFetcher:
    """Fetches cryptocurrency data from FreeCryptoAPI."""
    
    def __init__(self, db_path: Optional[str] = None, symbol: str = "BTCUSDT"):
        """
        Initialize the data fetcher.
        
        Args:
            db_path: Path to SQLite database. Defaults to data/btc_prices.db
            symbol: Trading pair symbol (e.g., BTCUSDT)
        """
        if db_path is None:
            # Azure Functions: Use /tmp (writable), Local: Use project data dir
            if IS_AZURE_FUNCTIONS:
                db_path = Path('/tmp') / 'btc_prices.db'
            else:
                db_path = get_project_root() / 'data' / 'btc_prices.db'
        else:
            db_path = Path(db_path)
        
        # Ensure data directory exists (skip if Azure Functions /tmp)
        try:
            if not IS_AZURE_FUNCTIONS or str(db_path.parent) != '/tmp':
                db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning(f"Could not create directory {db_path.parent}: {e}")
        
        self.db_path = str(db_path)
        self.symbol = symbol
        # Use Binance public API as it's more reliable
        self.base_url = "https://api.binance.com/api/v3"
        self.init_database()
    
    def init_database(self):
        """Initialize the SQLite database with prices table."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS prices (
                    timestamp INTEGER PRIMARY KEY,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL
                )
            ''')
            conn.commit()
            conn.close()
            logger.info(f"Database initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def _make_request(self, url: str, max_retries: int = 3) -> Dict:
        """
        Make HTTP request with retry logic.
        
        Args:
            url: API endpoint URL
            max_retries: Maximum number of retry attempts
            
        Returns:
            JSON response data
            
        Raises:
            requests.RequestException: If all retries fail
        """
        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"Request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s...")
                    sleep(wait_time)
                else:
                    logger.error(f"Request failed after {max_retries} attempts: {e}")
                    raise
    
    def fetch_current_price(self) -> Dict:
        """
        Fetch current price from Binance API.
        
        Returns:
            Dictionary with price, change_24h, and volume
            
        Raises:
            requests.RequestException: If API request fails
            KeyError: If API response structure is unexpected
        """
        # Binance 24hr ticker endpoint
        url = f"{self.base_url}/ticker/24hr?symbol={self.symbol}"
        
        try:
            data = self._make_request(url)
            
            # Binance API returns direct object (not nested in 'data')
            last_price = data.get('lastPrice')
            price_change = data.get('priceChangePercent', 0)
            volume = data.get('volume', 0)
            
            if last_price is None:
                raise ValueError(f"Could not extract price from API response: {data}")
            
            result = {
                'price': float(last_price),
                'change_24h': float(price_change),
                'volume': float(volume)
            }
            
            logger.info(f"Fetched current price for {self.symbol}: ${result['price']:,.2f}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch current price: {e}")
            raise
    
    def fetch_historical_data(self, days: int = 30, interval: str = "1h") -> pd.DataFrame:
        """
        Fetch historical K-line data from Binance.
        
        Args:
            days: Number of days of historical data to fetch
            interval: K-line interval (1h, 4h, 1d, etc.)
            
        Returns:
            DataFrame with OHLCV data
            
        Raises:
            requests.RequestException: If API request fails
        """
        limit = min(days * 24, 1000)  # Binance max limit is 1000
        url = f"{self.base_url}/klines?symbol={self.symbol}&interval={interval}&limit={limit}"
        
        try:
            klines = self._make_request(url)
            
            if not isinstance(klines, list) or not klines:
                raise ValueError("No historical data returned from API")
            
            # Binance returns: [
            #   [timestamp, open, high, low, close, volume, close_time, 
            #    quote_asset_volume, trades, taker_buy_base, taker_buy_quote, ignore]
            # ]
            # We only need the first 6 columns
            df = pd.DataFrame(klines)
            df = df.iloc[:, :6]  # Take only first 6 columns
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            
            # Convert timestamp from milliseconds to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', errors='coerce')
            
            # Convert numeric columns
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Remove rows with invalid data
            df = df.dropna()
            
            # Store in database
            self._store_to_database(df)
            
            logger.info(f"Fetched {len(df)} historical data points for {self.symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Failed to fetch historical data: {e}")
            raise
    
    def _store_to_database(self, df: pd.DataFrame):
        """Store DataFrame to SQLite database."""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Convert timestamp to integer (Unix timestamp in seconds)
            df_db = df.copy()
            df_db['timestamp'] = df_db['timestamp'].astype('int64') // 10**9
            
            # Use replace to update existing data
            df_db.to_sql('prices', conn, if_exists='replace', index=False)
            conn.commit()
            conn.close()
            
            logger.debug(f"Stored {len(df_db)} records to database")
        except Exception as e:
            logger.warning(f"Failed to store data to database: {e}")


# Test
if __name__ == "__main__":
    import sys
    
    # Setup logging for standalone execution
    logging.basicConfig(level=logging.INFO)
    
    try:
        fetcher = CryptoDataFetcher()
        current = fetcher.fetch_current_price()
        print(f"BTC Price: ${current['price']:,.2f} ({current['change_24h']:+.2f}%)")
        print(f"24h Volume: {current['volume']:,.2f}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

