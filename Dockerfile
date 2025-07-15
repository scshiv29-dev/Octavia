# Use official Python image
FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Install ffmpeg and system dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot and dashboard code
COPY bot/ ./bot/
COPY dashboard/ ./dashboard/
COPY musicbot.db ./

# Expose FastAPI port
EXPOSE 8000

# Default command (override in docker-compose)
CMD ["python", "-m", "bot.main"] 