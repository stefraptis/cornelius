# GPU base image is chosen with the provider in M2 (RunPod Serverless or Modal, EU region).
FROM python:3.11-slim
WORKDIR /app
COPY api/pyproject.toml api/pyproject.toml
COPY api/app api/app
RUN pip install --no-cache-dir ./api
COPY workers workers
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "workers.analysis.main"]
