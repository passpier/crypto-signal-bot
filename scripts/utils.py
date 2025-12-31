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
    
    Args:
        config_path: Path to config file. Defaults to config/config.yaml
        
    Returns:
        Configuration dictionary
    """
    if config_path is None:
        config_path = get_project_root() / 'config' / 'config.yaml'
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Override with environment variables if available
    if 'api_keys' in config:
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
    
    return config


def validate_config(config: dict) -> bool:
    """Validate that required configuration keys are present."""
    required_keys = [
        'api_keys.telegram_token',
        'api_keys.telegram_chat_id',
        'api_keys.gemini_api_key'
    ]
    
    for key_path in required_keys:
        keys = key_path.split('.')
        value = config
        try:
            for key in keys:
                value = value[key]
            if not value or value == f"YOUR_{key.upper()}_HERE":
                logger.warning(f"Missing or placeholder value for {key_path}")
                return False
        except KeyError:
            logger.error(f"Missing configuration key: {key_path}")
            return False
    
    return True

