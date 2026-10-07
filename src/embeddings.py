"""
Text embeddings with FastEmbed (runs locally on CPU, free, no API key).

Model: BAAI/bge-small-en-v1.5 -> 384 numbers per text.
The first run downloads the model (~70 MB) into .cache/fastembed in the project folder.
"""
import os

from src import config

# Windows without Developer Mode cannot create symlinks; the model cache still works, so hide the warning
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMENSIONS = 384
_model = None


def model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        cache = config.ROOT / ".cache" / "fastembed"
        cache.mkdir(parents=True, exist_ok=True)
        _model = TextEmbedding(MODEL_NAME, cache_dir=str(cache))
    return _model


def embed_passages(texts):
    """Embed document chunks. Returns a list of plain Python float lists."""
    return [v.tolist() for v in model().passage_embed(list(texts), batch_size=32)]


def embed_query(text):
    """Embed a user question (bge models use a slightly different form for queries)."""
    return next(iter(model().query_embed([text]))).tolist()
