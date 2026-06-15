# SuoraFlow — Project Memory (CLAUDE.md)

> This file is auto-loaded by Claude Code on every session. Keep it accurate.
> If you change the stack, a command, or a convention, update this file in the same commit.

## What this is

SuoraFlow is a **local-first, multimodal media-processing pipeline**. It ingests raw
audio/video, runs an audio-understanding pipeline (VAD → ASR → optional speaker
diarization → transcript chunking → semantic embedding), indexes everything in pgvector,
and lets a user search footage by meaning and assemble a rough-cut timeline.

The product framing is "AI-assisted footage search for editors." The **engineering
substance** is a reproducible audio/sensor data pipeline. Treat the audio path as the
first-class citizen — it is the part that matters most.

**Non-negotiable goal:** a fresh clone runs with a single `docker compose up`, with no
manual model downloads and no cloud credentials required. Diarization and any cloud
features must degrade gracefully when their tokens are absent.

## Stack (do not deviate without updating this file)

- **Frontend:** Vite + React 18 + TypeScript + Tailwind. SPA only, no SSR.
- **Backend:** FastAPI + SQLModel + Uvicorn (Python 3.11).
- **DB:** PostgreSQL 16 + pgvector (`pgvector/pgvector:pg16`).
- **Queue:** Redis 7 + RQ (NOT Celery).
- **Worker:** RQ worker, same Python image/codebase as backend (shares models + services).
- **Media:** FFmpeg + ffprobe (installed via apt in the backend/worker image).
- **ASR:** `faster-whisper`, device=cpu, compute_type=int8, model size from env (default `base`).
- **VAD:** Silero VAD via faster-whisper's built-in `vad_filter=True`.
- **Diarization (optional):** `pyannote.audio`, gated on `HF_TOKEN`. If absent, label all
  segments "Speaker 1" and continue — never fail the pipeline.
- **Text embeddings:** `sentence-transformers` `all-MiniLM-L6-v2` (384-dim).
- **Storage:** local filesystem under `STORAGE_ROOT`, mounted as a Docker volume.

## Repository layout

```
suoraflow/
  docker-compose.yml          # db, redis, backend, worker, frontend
  .env.example                # every var documented, safe defaults
  README.md                   # quickstart: clone -> docker compose up -> open localhost
  backend/
    Dockerfile                # python:3.11-slim + ffmpeg
    pyproject.toml
    app/
      main.py config.py database.py
      models/        # SQLModel tables
      schemas/       # request/response Pydantic models (separate from tables)
      routes/        # thin: validate -> call service -> return schema
      services/      # all business logic lives here
      workers/       # queue.py (RQ setup), tasks.py (process_asset pipeline)
      utils/         # ffmpeg.py, file_validation.py, security.py
    tests/           # pytest, mirrors app/ structure
  worker/
    worker.py        # RQ worker entrypoint (imports app.workers.tasks)
  frontend/
    package.json vite.config.ts tsconfig.json
    src/{pages,components,lib}/
  storage/           # raw/ audio/ frames/ clips/ exports/ (gitignored, volume-mounted)
  scripts/           # init_db.py, seed_demo.py, warm_models.py
```

## The processing pipeline (the heart of the project)

`process_asset(asset_id)` runs in the **worker**, never in the request lifecycle. It moves
the asset through these statuses, persisting after each step so the UI can poll:

`uploaded → probing → extracting_audio → vad → transcribing → diarizing → chunking → embedding → ready` (or `failed`).

1. **probe** — `ffprobe` JSON: duration, width, height, fps, codec, **audio sample rate,
   channels, codec**. Persist all audio fields; the UI surfaces them.
2. **extract_audio** — FFmpeg to mono 16 kHz WAV. Argument-array subprocess only.
3. **vad** — Silero VAD to find speech regions; store speech ratio + segment count.
4. **transcribe** — faster-whisper with `vad_filter=True`, word timestamps on.
5. **diarize** — pyannote if `HF_TOKEN` present; map speaker turns onto transcript
   segments. Otherwise single-speaker fallback.
6. **chunk** — group segments into 20–60s chunks on sentence-ish boundaries; keep
   start/end times.
7. **embed** — MiniLM embedding per chunk → pgvector. Search embeds the query and runs
   cosine/`<=>` similarity.

## Hard safety rules (these are graded by the reviewer agent)

- Never trust uploaded filenames. Generate `storage/raw/{project_id}/{asset_id}.{ext}`
  with a UUID asset id. Validate extension AND ffprobe-confirmed media type.
- Subprocess only via argument arrays. **Never** `shell=True`, `os.system`, or string
  interpolation into commands.
- Enforce `MAX_UPLOAD_MB`. Stream uploads to disk; do not read whole files into memory.
- CORS restricted to `FRONTEND_URL`. No `*` wildcard.
- All config via env vars (`.env`), never hardcoded. Ship `.env.example`.
- On any pipeline failure: set status `failed`, store a short safe `error_message`,
  never crash the worker process or leak stack traces / transcript bodies into logs.
- Media lives outside any web-served public directory.

## Definition of Done (per phase, enforced before moving on)

A phase is DONE only when ALL hold:
1. Code compiles / type-checks (`mypy` backend optional, `tsc --noEmit` frontend).
2. `docker compose up` brings the whole stack healthy from a clean state.
3. New backend logic has pytest coverage; `pytest` is green.
4. The phase's user-visible path passes a Playwright e2e run via the qa-tester agent.
5. The reviewer agent has signed off on the diff (security + the rules above).
6. CLAUDE.md and README reflect any new commands or env vars.

## Commands

- Run everything: `docker compose up --build`
- Backend tests: `docker compose run --rm backend pytest -q`
- Type-check frontend: `docker compose run --rm frontend npx tsc --noEmit`
- Warm models (first run): `docker compose run --rm worker python scripts/warm_models.py`
- Seed demo project: `docker compose run --rm backend python scripts/seed_demo.py`

## Working agreements

- Small, reviewable commits — one logical change each, conventional-commit messages.
- Routes stay thin; logic lives in `services/`. No business logic in route handlers.
- Schemas (`schemas/`) are distinct from tables (`models/`). Never return a table directly.
- Leave clean stubs for deferred features: `services/visual_search_service.py`,
  `services/rough_cut_service.py`. Stubs raise `NotImplementedError` with a clear message.
- Do not build visual/CLIP search or rough-cut generation until Phases 0–5 are DONE.
