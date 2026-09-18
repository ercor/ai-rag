"""DocumentSource port — discovers documents from a storage backend."""

from typing import Protocol


class DocumentSource(Protocol):
    """Scans a document source and returns metadata for each discoverable file.

    Implementations: filesystem, S3, SharePoint, etc.
    """

    async def scan(self) -> list[dict]:
        """Return a list of document metadata dicts.

        Each dict must contain at minimum:
          - path: str — location to pass to Parser.parse()
          - title: str — human-readable document title
        """
        ...
