"""Port interfaces for hexagonal architecture.

Each port defines a Protocol that adapters must implement.
The core application depends only on these protocols, never on
concrete adapter implementations.
"""

from src.ports.answer_repository import AnswerRepository
from src.ports.chunker import Chunker
from src.ports.citation_validator import CitationValidator
from src.ports.document_source import DocumentSource
from src.ports.embedder import Embedder
from src.ports.generator import Generator
from src.ports.models import Chunk
from src.ports.parser import Parser
from src.ports.search_index import SearchIndex

__all__ = [
    "Chunk",
    "DocumentSource",
    "Parser",
    "Chunker",
    "Embedder",
    "SearchIndex",
    "Generator",
    "CitationValidator",
    "AnswerRepository",
]
