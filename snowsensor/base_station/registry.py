"""Station registry — list of senders this base station accepts."""

from __future__ import annotations

from collections.abc import Iterable

from snowsensor.base_station.config import StationEntry


class StationRegistry:
    """Looks up sender station IDs against a configured allowlist.

    Adding a new station means adding an entry to receiver.yaml's `stations:`
    list — no code change. Unknown sender IDs are rejected (no ACK sent).
    """

    def __init__(self, stations: Iterable[StationEntry]) -> None:
        self._by_id: dict[str, StationEntry] = {s.id: s for s in stations}

    def is_known(self, station_id: str) -> bool:
        return station_id in self._by_id

    def label_for(self, station_id: str) -> str:
        entry = self._by_id.get(station_id)
        return entry.label if entry else ""

    def known_ids(self) -> list[str]:
        return list(self._by_id.keys())

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, station_id: object) -> bool:
        return isinstance(station_id, str) and station_id in self._by_id
