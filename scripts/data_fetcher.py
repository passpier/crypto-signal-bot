"""Data fetching module for cryptocurrency price data."""
import requests
from typing import Dict
import pandas as pd
import logging
from time import sleep
import sys

logger = logging.getLogger(__name__)

_CANDLES_PER_DAY = {
    '1m':  1440,
    '3m':   480,
    '5m':   288,
    '15m':   96,
    '30m':   48,
    '1h':    24,
    '2h':    12,
    '4h':     6,
    '6h':     4,
    '8h':     3,
    '12h':    2,
    '1d':     1,
    '3d':     0,   # <1/day; not usable with day-based logic
    '1w':     0,
}

BINANCE_MAX_CANDLES = 1000


class CryptoDataFetcher:
    """Fetches cryptocurrency data from Binance."""

    def __init__(self, symbol: str = "BTCUSDT"):
        """
        Initialize the data fetcher.

        Args:
            symbol: Trading pair symbol (e.g., BTCUSDT)
        """
        self.symbol = symbol
        self.base_url = "https://api.binance.com/api/v3"

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
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limited by Binance. Waiting {retry_after}s...")
                    sleep(retry_after)
                    continue
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

    def _candles_per_day(self, interval: str) -> int:
        """Return number of candles produced per calendar day for a given interval."""
        cpd = _CANDLES_PER_DAY.get(interval)
        if cpd is None:
            raise ValueError(f"Unknown interval: '{interval}'")
        if cpd == 0:
            raise ValueError(f"Unsupported sub-daily interval (< 1 candle/day): '{interval}'")
        return cpd

    def fetch_historical_data(self, days: int = 30, interval: str = "1h") -> pd.DataFrame:
        """
        Fetch historical K-line (OHLCV) data from Binance.

        Args:
            days:     Requested number of calendar days of history.
                      The actual number returned may be less if the request
                      exceeds Binance's 1000-candle-per-request limit.
            interval: Binance K-line interval string ('1m', '5m', '15m',
                      '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d').

        Returns:
            DataFrame with columns [timestamp, open, high, low, close, volume].
            Rows are sorted oldest → newest.

        Raises:
            ValueError: If interval is unsupported.
            requests.RequestException: If the Binance API request fails.
        """
        candles_per_day = self._candles_per_day(interval)
        requested_candles = days * candles_per_day
        limit = min(requested_candles, BINANCE_MAX_CANDLES)

        actual_days = limit // candles_per_day
        if actual_days < days:
            logger.warning(
                f"fetch_historical_data: requested {days}d but Binance caps at "
                f"{BINANCE_MAX_CANDLES} candles — returning ~{actual_days}d "
                f"({limit} candles @ {interval})"
            )
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

            logger.info(f"Fetched {len(df)} historical data points for {self.symbol}")
            return df

        except Exception as e:
            logger.error(f"Failed to fetch historical data: {e}")
            raise


# Test
if __name__ == "__main__":
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
