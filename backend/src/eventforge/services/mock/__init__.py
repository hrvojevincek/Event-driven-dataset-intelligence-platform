from eventforge.services.legacy.embedding import EmbeddingClient, get_embedding_client
from eventforge.services.mock.embedding import MockEmbeddingClient

__all__ = [
    "EmbeddingClient",
    "MockEmbeddingClient",
    "get_embedding_client",
]
