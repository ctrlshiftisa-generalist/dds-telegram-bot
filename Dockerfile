FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory (will be overridden by Railway Volume mount)
RUN mkdir -p /data

# Default database path for Railway (volume mounted at /data)
ENV DATABASE_PATH=/data/bot.db

CMD ["python", "-m", "bot"]
