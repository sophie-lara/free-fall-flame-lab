"""Page-preserving document indexing and retrieval interfaces."""

from .chunk import chunk_page
from .models import ChunkRecord, PageRecord
from .store import DocumentStore

__all__ = ["ChunkRecord", "DocumentStore", "PageRecord", "chunk_page"]
