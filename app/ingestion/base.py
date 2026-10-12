"""Base Ingestion Worker with resilient HTTP client and error handling."""
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import httpx
from app.logging import logger


class BaseIngestor(ABC):
    """Abstract base class for all Rotterdam Live data ingestors."""

    def __init__(self, name: str, timeout_seconds: float = 20.0):
        self.name = name
        self.timeout_seconds = timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self, verify_ssl: bool = True) -> httpx.AsyncClient:
        """Get or initialize persistent HTTP client with connection pooling."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if (
            self._client is None
            or self._client.is_closed
            or getattr(self, "_loop", None) is not current_loop
        ):
            if self._client and not self._client.is_closed:
                try:
                    await self._client.aclose()
                except Exception:
                    pass
            self._loop = current_loop
            self._client = httpx.AsyncClient(
                verify=verify_ssl,
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": f"RotterdamLive-Ingestor/{self.name}"},
                limits=httpx.Limits(max_keepalive_connections=15, max_connections=30),
            )
        return self._client

    async def close(self) -> None:
        """Close persistent HTTP client."""
        if self._client and not self._client.is_closed:
            try:
                await self._client.aclose()
            except Exception:
                pass
        self._client = None
        self._loop = None

    async def run_with_retry(
        self,
        max_retries: int = 3,
        initial_backoff: float = 2.0,
    ) -> Any:
        """Execute ingestion cycle with exponential backoff on transient errors."""
        attempt = 0
        backoff = initial_backoff
        while attempt < max_retries:
            try:
                logger.info("Starting ingestion cycle for '{}'", self.name)
                result = await self.ingest()
                logger.info("Successfully completed ingestion cycle for '{}'", self.name)
                return result
            except Exception as e:
                attempt += 1
                if attempt >= max_retries:
                    logger.error(
                        "Ingestion '{}' failed after {} attempts: {}",
                        self.name,
                        max_retries,
                        e,
                    )
                    raise
                logger.warning(
                    "Ingestion '{}' attempt {}/{} failed ({}), retrying in {:.1f}s...",
                    self.name,
                    attempt,
                    max_retries,
                    e,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff *= 2.0

    @abstractmethod
    async def ingest(self) -> Dict[str, Any]:
        """Core ingestion logic to be implemented by each data source."""
        pass
