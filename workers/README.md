# Workers

Background processes that take jobs from the `jobs` table (Postgres) and
write results back. Video bytes move between object storage and the worker,
never through the API.

| Worker | Milestone | Runs on | Does |
| --- | --- | --- | --- |
| `transcode` | M1 | CPU container (ffmpeg) | Anonymization, HLS renditions (720p, 480p), poster, sprite sheet, proxy, SHA-256 |
| `analysis` | M2 | Serverless GPU (EU region) | Wraps the published LC pipeline unchanged: EfficientNet-V2-S, Bi-LSTM, scene-event heuristics, highlights, report |

`common/` holds the shared job loop (`claim_next_job`, retries, heartbeat)
and the storage client, which is the API's `storage.py` installed as a
package so there is exactly one place that talks to object storage.

Each worker is a Docker image. Run locally with `docker compose up transcode`,
or without Docker from the repository root (ffmpeg must be on PATH):

```
pip install -e "api[workers]"
python -m workers.transcode.main
```

Transcode settings (environment): `ORIGINAL_RETENTION_DAYS` (default 90) and
the out-of-body thresholds `OOB_MIN_RED_DOMINANCE`, `OOB_MAX_BRIGHTNESS`,
`OOB_MIN_SATURATION`, `OOB_MIN_RUN_S`, `OOB_PAD_S`.
