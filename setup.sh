#!/bin/bash
# Setup script for crypto-signal-bot

set -e

echo "🚀 Setting up Crypto Signal Bot..."

# Create directories
echo "📁 Creating directories..."
mkdir -p data logs n8n_data

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "🐍 Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env file from template..."
    cat > .env << EOF
# Telegram Bot Configuration
TELEGRAM_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Google Gemini API
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: Override config file paths
CONFIG_PATH=config/config.yaml
EOF
    echo "⚠️  Please edit .env file with your API keys!"
fi

echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your API keys"
echo "2. Or edit config/config.yaml"
echo "3. Run: python scripts/main.py"
echo "4. Or start n8n: docker-compose up -d"

