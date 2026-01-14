from typing import override

from sqlalchemy.ext.asyncio import AsyncEngine

from .api.models.health import Health
from .database.postgres.repository import is_healthy
from .services.service_handler import HealthHandler


class DatabaseHealthHandler(HealthHandler):
    def __init__(self, engine: AsyncEngine) -> None:
        super().__init__("database")
        self._engine = engine

    @override
    async def get_health(self) -> Health:
        if await is_healthy(self._engine):
            return Health.UP
        else:
            return Health.DOWN
