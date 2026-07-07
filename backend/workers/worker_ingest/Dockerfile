FROM python:3.12-slim
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# YouTube rotates its player/signature format every few weeks and yt-dlp ships
# fixes just as often; a pinned version rots into "Requested format is not
# available" errors. Force the latest at build time (overrides the requirements
# pin) so every rebuild of the ONLY service that runs yt-dlp is current.
RUN pip install --no-cache-dir --upgrade "yt-dlp[default]"
COPY . .
CMD ["python", "-m", "backend.workers.worker_ingest"]
