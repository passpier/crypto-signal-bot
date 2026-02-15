FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Taipei

# Default command: Run Flask app with gunicorn
# Port is set by Cloud Run via $PORT environment variable
CMD exec gunicorn --bind :${PORT:-8080} --workers 1 --threads 2 --timeout 600 app:app

