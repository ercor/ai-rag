"""Application configuration via pydantic-settings.

All settings are loaded from environment variables with sensible defaults
for local Docker Compose development.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the ai-rag backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://rag:rag@localhost:5432/rag"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5"
    ollama_embed_model: str = "nomic-embed-text"

    # Ingestion
    watch_dir: str = "./data/docs"
    ingest_concurrency: int = 2
    embed_batch_size: int = 64
    embed_batch_size_gpu: int = 256  # Larger batches when GPU is available

    # GPU Configuration
    gpu_enabled: bool = False  # Auto-detect or manually enable GPU acceleration

    # Retrieval
    retrieval_top_k: int = 5
    min_score_threshold: float = 0.0

    # Adapter selectors (for future multi-adapter support)
    embedder_adapter: str = "ollama"
    generator_adapter: str = "ollama"

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Per-type chunking configuration
    chunk_min_pdf: int = 200
    chunk_max_pdf: int = 600
    chunk_overlap_pdf: int = 50
    chunk_min_md: int = 200
    chunk_max_md: int = 600
    chunk_overlap_md: int = 50
    chunk_min_docx: int = 200
    chunk_max_docx: int = 600
    chunk_overlap_docx: int = 50
    chunk_min_html: int = 200
    chunk_max_html: int = 600
    chunk_overlap_html: int = 50
    chunk_min_txt: int = 200
    chunk_max_txt: int = 600
    chunk_overlap_txt: int = 50

    def get_chunking_config(self, source_type: str) -> dict:
        """Return chunking config for a given source type.

        Maps file extensions to per-type settings. Unknown types
        fall back to txt defaults.
        """
        type_map = {
            ".pdf": ("pdf", self.chunk_min_pdf, self.chunk_max_pdf, self.chunk_overlap_pdf),
            ".md": ("md", self.chunk_min_md, self.chunk_max_md, self.chunk_overlap_md),
            ".docx": ("docx", self.chunk_min_docx, self.chunk_max_docx, self.chunk_overlap_docx),
            ".html": ("html", self.chunk_min_html, self.chunk_max_html, self.chunk_overlap_html),
            ".htm": ("html", self.chunk_min_html, self.chunk_max_html, self.chunk_overlap_html),
            ".txt": ("txt", self.chunk_min_txt, self.chunk_max_txt, self.chunk_overlap_txt),
        }

        # Normalize source_type: accept both ".pdf" and "pdf"
        key = source_type if source_type.startswith(".") else f".{source_type}"
        entry = type_map.get(key)

        if entry is None:
            # Fall back to txt defaults
            return {
                "min_tokens": self.chunk_min_txt,
                "max_tokens": self.chunk_max_txt,
                "overlap": self.chunk_overlap_txt,
            }

        _, min_t, max_t, overlap = entry
        return {
            "min_tokens": min_t,
            "max_tokens": max_t,
            "overlap": overlap,
        }

    async def detect_gpu_available(self) -> bool:
        """Detect if Ollama has GPU acceleration available.

        Queries Ollama's /api/version endpoint and checks system info.
        Returns True if GPU is detected, False otherwise.
        """
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Query Ollama system info
                response = await client.get(f"{self.ollama_base_url}/api/version")
                response.raise_for_status()

                # Ollama doesn't expose GPU info directly via API,
                # so we check if the system has GPU capabilities
                # by attempting to load a model with GPU requirements
                # For now, we rely on the gpu_enabled config flag
                # In production, you'd check nvidia-smi or similar

                # Check if NVIDIA GPU is available via system
                import subprocess

                try:
                    result = subprocess.run(
                        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                        capture_output=True,
                        text=True,
                        timeout=2.0,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        return True
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pass

                return False
        except Exception:
            return False

    def get_effective_embed_batch_size(self, gpu_available: bool = False) -> int:
        """Return the optimal embedding batch size based on GPU availability.

        Uses larger batches when GPU is available for better throughput.
        """
        if gpu_available or self.gpu_enabled:
            return self.embed_batch_size_gpu
        return self.embed_batch_size


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
