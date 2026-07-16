# Playwright's official image ships Chromium + all OS deps preinstalled (Python 3.12 on Ubuntu Noble).
# This avoids the fragile `playwright install --with-deps` step that breaks on Debian trixie.
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg unzip curl && rm -rf /var/lib/apt/lists/*

# JS runtime for yt-dlp. Without it, YouTube's 720p/1080p DASH formats are hidden
# and yt-dlp falls back to the 360p combined stream — at which resolution a jersey
# number renders ~15px tall and is unreadable (EAGLE EYE then upscales blur). deno
# lets yt-dlp extract the HD formats so there are real pixels to read.
RUN curl -fsSL https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip -o /tmp/deno.zip \
    && unzip -o /tmp/deno.zip -d /usr/local/bin && rm /tmp/deno.zip && chmod +x /usr/local/bin/deno

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# YouTube rotates its player/signature format every few weeks and yt-dlp ships
# fixes just as often; a pinned version rots into "Requested format is not
# available" errors on the ingest worker. Force the latest at build time so every
# rebuild is current (harmless for the services that never call yt-dlp). This is
# the image ALL services build from — the ingest worker overrides the start
# command to run backend.workers.worker_ingest.
RUN pip install --no-cache-dir --upgrade "yt-dlp[default]"

# Browsers are already installed in the base image at $PLAYWRIGHT_BROWSERS_PATH.

# Copy into backend/ subdirectory so "from backend.X import Y" works
COPY . backend/

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 4"]
