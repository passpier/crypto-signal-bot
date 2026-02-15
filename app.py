"""Flask HTTP server entry point for Google Cloud Run deployment."""
import logging
import os
import sys
from pathlib import Path
from flask import Flask, jsonify

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from scripts.utils import validate_config, load_config

# Initialize Flask app
app = Flask(__name__)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for Cloud Run."""
    return jsonify({'status': 'healthy', 'service': 'crypto-signal-bot'}), 200


@app.route('/trigger', methods=['POST'])
def trigger():
    """Trigger endpoint for Cloud Scheduler."""
    logger.info('=' * 60)
    logger.info('Crypto Signal Bot Triggered via Cloud Scheduler')
    logger.info('=' * 60)

    try:
        # Load configuration
        config = load_config()
        if not validate_config(config):
            error_msg = 'Invalid or missing configuration'
            logger.error(error_msg)
            return jsonify({'error': error_msg}), 400

        # Import and run the bot main function
        from scripts.main import main as bot_main

        # Run the bot main function
        exit_code = bot_main()

        if exit_code == 0:
            logger.info('Bot execution completed successfully')
            return jsonify({'status': 'success', 'message': 'Bot execution completed'}), 200
        else:
            error_msg = f'Bot execution failed with exit code: {exit_code}'
            logger.error(error_msg)
            return jsonify({'status': 'error', 'message': error_msg}), 500

    except ImportError as e:
        logger.error(f'Import error - check deployment structure: {e}', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500
    except Exception as e:
        logger.error(f'Function execution failed: {e}', exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    # Get port from environment variable or default to 8080
    port = int(os.getenv('PORT', 8080))
    logger.info(f'Starting Flask server on port {port}')
    app.run(host='0.0.0.0', port=port, debug=False)
