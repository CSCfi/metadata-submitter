from typing import Callable, override

from .api.models.health import Health
from .database.postgres.repository import SessionFactory, is_healthy
from .services.service_handler import HealthHandler


class DatabaseHealthHandler(HealthHandler):
    def __init__(self, session_factory_provider: Callable[[], SessionFactory]) -> None:
        super().__init__("database")
        self._session_factory_provider = session_factory_provider

    @override
    async def get_health(self) -> Health:
        if await is_healthy(self._session_factory_provider):
            return Health.UP
        else:
            return Health.DOWN
