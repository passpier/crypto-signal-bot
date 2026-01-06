"""Utility functions for crypto signal bot."""
import os
import logging
from pathlib import Path
from typing import Optional
import yaml
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


def load_config(config_path: Optional[str] = None) -> dict:
    """
    Load configuration from YAML file, with environment variable overrides.
    Supports Azure Functions mode where config file may not exist.
    
    Args:
        config_path: Path to config file. Defaults to config/config.yaml
        
    Returns:
        Configuration dictionary
    """
    if config_path is None:
        config_path = get_project_root() / 'config' / 'config.yaml'
    else:
        config_path = Path(config_path)
    
    # Try to load from YAML file if it exists
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    else:
        # Azure Functions mode: create config from environment variables
        logger.info("Config file not found, loading from environment variables (Azure Functions mode)")
        config = {
            'api_keys': {},
            'trading': {},
            'indicators': {}
        }
    
    # Build config structure, prioritizing environment variables
    config.setdefault('api_keys', {})
    config.setdefault('trading', {})
    config.setdefault('indicators', {})
    
    # Load from environment variables (Azure Functions App Settings)
    # These override YAML values if present
    config['api_keys']['telegram_token'] = os.getenv(
        'TELEGRAM_TOKEN', 
        config['api_keys'].get('telegram_token', '')
    )
    config['api_keys']['telegram_chat_id'] = os.getenv(
        'TELEGRAM_CHAT_ID',
        config['api_keys'].get('telegram_chat_id', '')
    )
    config['api_keys']['gemini_api_key'] = os.getenv(
        'GEMINI_API_KEY',
        config['api_keys'].get('gemini_api_key', '')
    )
    
    # Trading settings from environment
    config['trading']['symbol'] = os.getenv(
        'TRADING_SYMBOL',
        config['trading'].get('symbol', 'BTCUSDT')
    )
    config['trading']['interval'] = os.getenv(
        'TRADING_INTERVAL',
        config['trading'].get('interval', '1h')
    )
    config['trading']['stop_loss_percent'] = float(os.getenv(
        'STOP_LOSS_PERCENT',
        config['trading'].get('stop_loss_percent', 3)
    ))
    config['trading']['take_profit_percent'] = float(os.getenv(
        'TAKE_PROFIT_PERCENT',
        config['trading'].get('take_profit_percent', 6)
    ))
    
    # Indicator settings (with defaults)
    config['indicators'].setdefault('rsi_period', 14)
    config['indicators'].setdefault('rsi_oversold', 30)
    config['indicators'].setdefault('rsi_overbought', 70)
    config['indicators'].setdefault('macd_fast', 12)
    config['indicators'].setdefault('macd_slow', 26)
    config['indicators'].setdefault('macd_signal', 9)
    
    return config


def validate_config(config: dict) -> bool:
    """
    Validate that required configuration keys are present.
    
    Note: gemini_api_key is optional (sentiment analysis will be skipped if missing)
    """
    required_keys = [
        'api_keys.telegram_token',
        'api_keys.telegram_chat_id'
    ]
    
    optional_keys = [
        'api_keys.gemini_api_key'
    ]
    
    # Check required keys
    for key_path in required_keys:
        keys = key_path.split('.')
        value = config
        try:
            for key in keys:
                value = value[key]
            if not value or value == f"YOUR_{key.upper()}_HERE":
                logger.error(f"Missing or placeholder value for required key: {key_path}")
                return False
        except KeyError:
            logger.error(f"Missing required configuration key: {key_path}")
            return False
    
    # Check optional keys (warn but don't fail)
    for key_path in optional_keys:
        keys = key_path.split('.')
        value = config
        try:
            for key in keys:
                value = value[key]
            if not value or value == f"YOUR_{key.upper()}_HERE":
                logger.warning(f"Optional key {key_path} not set - sentiment analysis will be skipped")
        except KeyError:
            logger.warning(f"Optional configuration key missing: {key_path} - sentiment analysis will be skipped")
    
    return True

