FROM python:3.12-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install headless Chromium + OS deps for Hudl stream capture (Playwright)
RUN python -m playwright install --with-deps chromium

# Copy into backend/ subdirectory so "from backend.X import Y" works
COPY . backend/

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 4"]
