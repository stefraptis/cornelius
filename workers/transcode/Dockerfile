FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY api/pyproject.toml api/pyproject.toml
COPY api/app api/app
RUN pip install --no-cache-dir ./api
COPY workers workers
ENV PYTHONUNBUFFERED=1
USER nobody
CMD ["python", "-m", "workers.transcode.main"]
