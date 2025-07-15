# Octavia Music Bot

A music bot project with a FastAPI backend, built with Python 3.11, Docker, and ffmpeg. The project includes a bot and a dashboard, and uses a SQLite database (`musicbot.db`).

## Features
- Music bot functionality (see `bot/`)
- Dashboard for management (see `dashboard/`)
- FastAPI backend (exposed on port 8000)
- Dockerized for easy deployment

## Requirements
- Docker (recommended)
- Or: Python 3.11, ffmpeg, pip

## Quick Start (Docker)

1. **Build the Docker image:**
   ```sh
   docker build -t octavia-musicbot .
   ```
2. **Run the container:**
   ```sh
   docker run -p 8000:8000 octavia-musicbot
   ```

## Manual Setup (Without Docker)

1. Install Python 3.11 and ffmpeg.
2. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```
3. Run the bot:
   ```sh
   python -m bot.main
   ```

## Project Structure
```
.
├── bot/           # Bot source code
├── dashboard/     # Dashboard source code
├── musicbot.db    # SQLite database
├── requirements.txt
├── Dockerfile
└── README.md
```

## License
MIT 