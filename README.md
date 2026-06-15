# SuoraFlow

AI-assisted footage search for editors. Local-first, multimodal media-processing pipeline:
VAD → ASR → diarization → semantic search over your footage.

## Quickstart

```bash
git clone <repo-url> suoraflow
cd suoraflow
cp .env.example .env          # review defaults; change passwords for production
docker compose up --build     # first run downloads ~1 GB of models — be patient
```

Open http://localhost:5173 — the frontend loads and displays the backend health status.

API is at http://localhost:8000.

## Stopping

```bash
docker compose down           # stop containers, keep volumes (data + model cache)
docker compose down -v        # also remove volumes (full reset)
```

> **Upgrading from an early build?** The `model_cache` and `storage` volumes are seeded
> writable for the non-root container user only when first created. If you have volumes
> from before that fix and hit a permission error while warming models, run
> `docker compose down -v` once to recreate them.

## Commands

| Task | Command |
|------|---------|
| Run everything | `docker compose up --build` |
| Backend tests | `docker compose run --rm backend pytest -q` |
| Type-check frontend | `docker compose run --rm frontend npx tsc --noEmit` |
| Pre-warm model cache | `docker compose run --rm worker python scripts/warm_models.py` |
| Seed demo data | `docker compose run --rm backend python scripts/seed_demo.py` |

## Environment variables

See `.env.example` for the full list with documentation. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `suoraflow` | PostgreSQL user |
| `POSTGRES_PASSWORD` | `suoraflow_secret` | PostgreSQL password |
| `POSTGRES_DB` | `suoraflow` | Database name |
| `DATABASE_URL` | *(internal)* | Full DSN for backend |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `FRONTEND_URL` | `http://localhost:5173` | Allowed CORS origin |
| `VITE_API_URL` | `http://localhost:8000` | Backend URL for browser |
| `STORAGE_ROOT` | `/storage` | Where media files live |
| `MAX_UPLOAD_MB` | `500` | Upload size limit |
| `WHISPER_MODEL` | `base` | faster-whisper model size |
| `HF_TOKEN` | *(empty)* | HuggingFace token; leave blank to skip diarization |

## Ports

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **PostgreSQL**: 5432 (internal only)
- **Redis**: 6379 (internal only)

## Architecture

```
Browser → Vite SPA → FastAPI backend → PostgreSQL + pgvector
                                     → Redis (RQ queue)
                                            ↓
                                       RQ worker
                                       (ffmpeg → faster-whisper → sentence-transformers)
```

Storage lives on a Docker volume at `STORAGE_ROOT` — never inside a web-served directory.
