"""Generator port — produces streamed answer text from a prompt."""

from typing import AsyncIterator, Protocol


class Generator(Protocol):
    """Generates answer text by streaming tokens from an LLM.

    Implementations: Ollama (qwen2.5), OpenAI, etc.
    """

    async def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        """Yield answer tokens as they are generated.

        The caller is responsible for assembling tokens into a complete
        answer and running citation validation.
        """
        ...
