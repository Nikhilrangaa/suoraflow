# SuoraFlow — Kickoff Prompt (paste into Claude Code, in Plan Mode, on Opus)

You are the lead architect and orchestrator for a project called **SuoraFlow**. I have set
up `CLAUDE.md` and four subagents (`coder`, `debugger`, `qa-tester`, `reviewer`). Read
`CLAUDE.md` now; it is the source of truth for stack, layout, and safety rules.

**Do not write code yet.** First produce a concrete, phase-by-phase build plan with a
checklist I can approve. Then, once I approve, execute it phase by phase, delegating to the
subagents per the workflow below.

## Product (read carefully — framing matters)

SuoraFlow is a **local-first, multimodal media-processing pipeline**, demoed as
"AI-assisted footage search for video editors," but the part that matters is the
**audio-understanding pipeline**: ingest raw A/V → VAD → ASR → optional diarization →
transcript chunking → semantic embedding → vector search → rough-cut timeline.

The single hard requirement: a fresh `git clone` runs end to end with **one
`docker compose up`**, no manual model downloads (cache weights in a named volume; the
first run is slow, every run after is instant), and no cloud credentials. Diarization
(pyannote) is optional and gated on `HF_TOKEN` — if the token is absent, label everything
"Speaker 1" and keep going. Nothing cloud may be required to run or demo this.

Lead the audio path. Surface audio metadata in the UI (sample rate, channels, codec) and
render a waveform — this is a portfolio piece for an audio/sensor software engineering role,
and the audio fidelity is the thing a reviewer will judge.

## Stack (fixed — see CLAUDE.md for the full list)

Vite + React + TS + Tailwind · FastAPI + SQLModel · Postgres 16 + pgvector · Redis 7 + RQ ·
RQ worker sharing the backend image · FFmpeg/ffprobe · faster-whisper (CPU int8, `base`) ·
Silero VAD · pyannote (optional) · sentence-transformers `all-MiniLM-L6-v2` · local FS
storage via volume.

## Data models

Project, Asset, TranscriptSegment, TextEmbedding (pgvector), Clip, Timeline, TimelineItem.
Fields are in the spec I'll reference below; Asset must carry audio fields
(sample_rate, channels, audio_codec) plus status and error_message. Embeddings need a
vector index (ivfflat/hnsw) on the embedding column.

## API surface (MVP)

```
POST   /api/projects                                   GET /api/projects
GET    /api/projects/{id}                              DELETE /api/projects/{id}
POST   /api/projects/{id}/assets/upload                GET /api/projects/{id}/assets
GET    /api/assets/{id}        GET /api/assets/{id}/status   GET /api/assets/{id}/transcript
DELETE /api/assets/{id}
POST   /api/projects/{id}/search        # {query, limit} -> ranked timestamped chunks
POST   /api/projects/{id}/clips         GET /api/projects/{id}/clips
POST   /api/projects/{id}/timelines     GET /api/projects/{id}/timelines
POST   /api/timelines/{id}/items        DELETE /api/timelines/{id}/items/{item_id}
GET    /api/timelines/{id}/export       # ?format=json|csv
```

## Pipeline (in the worker, never in the request)

`uploaded → probing → extracting_audio → vad → transcribing → diarizing → chunking → embedding → ready` (or `failed`).
Persist status after each step. ffprobe metadata → mono 16kHz WAV → Silero VAD →
faster-whisper (vad_filter, word timestamps) → optional pyannote → 20–60s chunks → MiniLM
embeddings → pgvector. Search embeds the query and runs vector similarity.

## Build phases (plan around these; each ends at the Definition of Done in CLAUDE.md)

- **Phase 0 — Scaffold:** repo layout, docker-compose (db, redis, backend, worker,
  frontend), `.env.example`, healthchecks, README quickstart, `warm_models.py`. Acceptance:
  `docker compose up` brings all services healthy; `/health` returns ok; frontend loads.
- **Phase 1 — Projects + upload:** project CRUD; safe upload (UUID names, extension +
  ffprobe media-type validation, size limit, streamed to disk); Asset row created with
  status `uploaded`; job enqueued; dashboard + project page render.
- **Phase 2 — Audio pipeline + status:** worker runs probe → extract_audio → vad →
  transcribe → diarize(optional), persisting segments and audio metadata; status polling
  drives a live badge; asset page shows player, metadata, **waveform**, and a clickable
  transcript that seeks the video.
- **Phase 3 — Chunking + embeddings + semantic search:** chunk transcript, embed to
  pgvector with a vector index, implement search endpoint and the search UI with ranked,
  timestamped, click-to-seek results.
- **Phase 4 — Clips + timeline + export:** add results to a timeline, reorder/remove,
  export JSON and CSV.
- **Phase 5 — Polish + demo seed:** `seed_demo.py`, a committed short fixture clip, README
  demo script, clean empty/loading/error states.
- **Deferred (stubs only):** `visual_search_service.py` (CLIP frame search),
  `rough_cut_service.py` (script→beats→clips). Stub now, build later.

## Orchestration workflow (how to use the subagents)

You (Opus) stay in the main session as orchestrator and reviewer of plans. For each phase:
1. Restate the phase's acceptance criteria.
2. Delegate implementation to the **coder** agent in small scoped tasks.
3. When a user-visible path is done, delegate verification to the **qa-tester** agent
   (pytest + Playwright MCP).
4. On any failure, delegate to the **debugger** agent; loop coder↔debugger until green.
5. Before marking the phase DONE, delegate the diff to the **reviewer** agent; resolve all
   [blocking] items.
6. Commit, update CLAUDE.md/README if anything changed, then propose the next phase and
   wait for my go-ahead.

Now: read CLAUDE.md, then output the Phase 0 plan as a checklist and stop for my approval.
