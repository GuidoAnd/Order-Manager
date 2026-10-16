"""Estado temporal y acotado de navegación; separado de los datos de negocio."""

from collections import OrderedDict
from secrets import token_urlsafe
from threading import RLock
from time import monotonic

from .store import DomainError


class JourneyNavigation:
    max_entries = 64
    max_selections = 32768
    lifetime = 1800

    def __init__(self):
        self._entries = OrderedDict()
        self._lock = RLock()

    def _expire(self):
        now = monotonic()
        for token, (_, _, created) in list(self._entries.items()):
            if now - created >= self.lifetime:
                del self._entries[token]

    def save(self, journey_id: str, values: dict) -> str:
        with self._lock:
            self._expire()
            if len(values) > self.max_selections:
                raise DomainError("Demasiadas selecciones de páginas. Vuelve a Jornada para restablecerlas.", 413)
            while self._entries and (
                len(self._entries) >= self.max_entries
                or sum(len(entry[1]) for entry in self._entries.values()) + len(values) > self.max_selections
            ):
                self._entries.popitem(last=False)
            token = token_urlsafe(24)
            self._entries[token] = (journey_id, dict(values), monotonic())
            return token

    def load(self, token: str, journey_id: str) -> dict | None:
        with self._lock:
            self._expire()
            entry = self._entries.get(token)
            if entry is None or entry[0] != journey_id:
                return None
            self._entries.move_to_end(token)
            return dict(entry[1])
