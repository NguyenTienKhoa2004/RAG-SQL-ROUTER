"""Bounded, in-memory cache of retrieved nodes for one document index."""

from collections import OrderedDict
from copy import deepcopy
from threading import Lock
from time import monotonic
from typing import Any, Callable


class RetrievalCache:
    def __init__(
        self,
        retrieve: Callable[[str], list[Any]],
        max_entries: int = 128,
        ttl_seconds: float = 300,
    ):
        if max_entries <= 0 or ttl_seconds <= 0:
            raise ValueError("Cache capacity and TTL must be positive")
        self._retrieve = retrieve
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._entries: OrderedDict[str, tuple[float, list[Any]]] = OrderedDict()
        self._lock = Lock()

    def get(self, query: str) -> list[Any]:
        """Match exact query text; return copies so synthesis cannot alter the cache."""
        # Serialize lookups and retrieval to avoid duplicate searches on concurrent misses.
        with self._lock:
            now = monotonic()
            expired = [
                key for key, (expires_at, _) in self._entries.items()
                if expires_at <= now
            ]
            for key in expired:
                del self._entries[key]

            if query in self._entries:
                self._entries.move_to_end(query)
                print(
                    f"[RetrievalCache] HIT query={query!r} "
                    f"nodes={len(self._entries[query][1])} (using cached document context)",
                    flush=True,
                )
                return deepcopy(self._entries[query][1])

            print(
                f"[RetrievalCache] MISS query={query!r} (retrieving document context)",
                flush=True,
            )
            # Failed retrievals are not cached; empty successful results are cached.
            nodes = self._retrieve(query)
            self._entries[query] = (
                monotonic() + self._ttl_seconds,
                deepcopy(nodes),
            )
            if len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
            return nodes
