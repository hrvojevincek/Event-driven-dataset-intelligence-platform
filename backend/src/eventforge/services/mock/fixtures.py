import hashlib

from eventforge.events.schemas.constants import EMBEDDING_DIMENSION

MOCK_MODEL = "mock-local"


def deterministic_embedding(text: str, *, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    """Stable pseudo-embedding from text so legacy RAG tests return repeatable results."""
    seed = hashlib.sha256(text.encode()).digest()
    values: list[float] = []
    while len(values) < dimension:
        for byte in seed:
            values.append((byte / 127.5) - 1.0)
            if len(values) >= dimension:
                break
        seed = hashlib.sha256(seed).digest()
    return values
