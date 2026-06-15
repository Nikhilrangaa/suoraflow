"""
warm_models.py — Pre-download model weights into the shared cache volume.

Run before the first real pipeline job to avoid download latency during processing:
  docker compose run --rm worker python scripts/warm_models.py
"""
import os
import sys


def warm_whisper(model_size: str) -> None:
    print(f"[warm] Downloading faster-whisper model: {model_size}")
    from faster_whisper import WhisperModel  # type: ignore[import]

    WhisperModel(model_size, device="cpu", compute_type="int8")
    print(f"[warm] faster-whisper '{model_size}' ready.")


def warm_embeddings(model_name: str) -> None:
    print(f"[warm] Downloading sentence-transformers model: {model_name}")
    from sentence_transformers import SentenceTransformer  # type: ignore[import]

    SentenceTransformer(model_name)
    print(f"[warm] sentence-transformers '{model_name}' ready.")


if __name__ == "__main__":
    whisper_model = os.environ.get("WHISPER_MODEL", "base")
    embedding_model = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    try:
        warm_whisper(whisper_model)
    except Exception as exc:
        print(f"[warm] ERROR warming whisper: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        warm_embeddings(embedding_model)
    except Exception as exc:
        print(f"[warm] ERROR warming embeddings: {exc}", file=sys.stderr)
        sys.exit(1)

    print("[warm] All models ready.")
