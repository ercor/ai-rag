"""Unit tests for per-type chunking configuration.

Tests env var resolution for CHUNK_MIN_{TYPE}, CHUNK_MAX_{TYPE},
CHUNK_OVERLAP_{TYPE} for pdf, md, docx, html, txt.
"""



from src.config import Settings


class TestPerTypeChunkingConfig:
    """Test per-type chunking config resolution."""

    def test_default_chunking_values(self):
        """Default chunking config has sensible defaults for all types."""
        settings = Settings()
        assert settings.chunk_min_pdf == 200
        assert settings.chunk_max_pdf == 600
        assert settings.chunk_overlap_pdf == 50
        assert settings.chunk_min_md == 200
        assert settings.chunk_max_md == 600
        assert settings.chunk_overlap_md == 50
        assert settings.chunk_min_docx == 200
        assert settings.chunk_max_docx == 600
        assert settings.chunk_overlap_docx == 50
        assert settings.chunk_min_html == 200
        assert settings.chunk_max_html == 600
        assert settings.chunk_overlap_html == 50
        assert settings.chunk_min_txt == 200
        assert settings.chunk_max_txt == 600
        assert settings.chunk_overlap_txt == 50

    def test_env_override_pdf(self, monkeypatch):
        """CHUNK_MAX_PDF env var overrides default."""
        monkeypatch.setenv("CHUNK_MAX_PDF", "800")
        monkeypatch.setenv("CHUNK_MIN_PDF", "300")
        monkeypatch.setenv("CHUNK_OVERLAP_PDF", "75")
        settings = Settings()
        assert settings.chunk_max_pdf == 800
        assert settings.chunk_min_pdf == 300
        assert settings.chunk_overlap_pdf == 75

    def test_env_override_md(self, monkeypatch):
        """CHUNK_MAX_MD env var overrides default."""
        monkeypatch.setenv("CHUNK_MAX_MD", "500")
        settings = Settings()
        assert settings.chunk_max_md == 500

    def test_get_chunking_config_for_type(self):
        """get_chunking_config returns correct values for each type."""
        settings = Settings()
        for source_type in ("pdf", "md", "docx", "html", "txt"):
            config = settings.get_chunking_config(source_type)
            assert "min_tokens" in config
            assert "max_tokens" in config
            assert "overlap" in config
            assert config["min_tokens"] > 0
            assert config["max_tokens"] > config["min_tokens"]

    def test_get_chunking_config_unknown_type_returns_defaults(self):
        """Unknown content type falls back to txt defaults."""
        settings = Settings()
        config = settings.get_chunking_config("unknown")
        assert config["min_tokens"] == settings.chunk_min_txt
        assert config["max_tokens"] == settings.chunk_max_txt
