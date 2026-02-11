"""Health API handler."""

import asyncio

from ...helpers.logger import LOG
from ...services.service_handler import HealthHandler
from ..models.health import Health, ServiceHealth
from .restapi import RESTAPIHandler


class HealthAPIHandler(RESTAPIHandler):
    """Health API handler."""

    @staticmethod
    async def get_health(handler: HealthHandler) -> tuple[str, Health]:
        """
        Get service health.

        :param handler: The health handler.
        :returns: The service health.
        """

        try:
            return handler.service_name, await handler.get_health()
        except Exception:
            LOG.exception(
                "Unexpected error during health check for service '%s'",
                handler.service_name,
            )
            return handler.service_name, Health.ERROR

    async def get_health_status(self) -> ServiceHealth:
        """
        Get service health.
        """
        handlers: list[HealthHandler] = [
            self._handlers.datacite,
            self._handlers.pid,
            self._handlers.metax,
            self._handlers.ror,
            self._handlers.rems,
            self._handlers.auth,
            self._handlers.keystone,
            self._handlers.admin,
            self._handlers.database,
        ]

        results: list[tuple[str, Health]] = []

        async with asyncio.TaskGroup() as tg:
            tasks = {tg.create_task(self.get_health(h)): h for h in handlers if h is not None}
            for task in tasks:
                key, health = await task
                results.append((key, health))

        services = dict(results)

        if any(s == Health.DOWN for s in services.values()):
            status = Health.DOWN
        elif any(s == Health.ERROR for s in services.values()):
            status = Health.ERROR
        elif any(s == Health.DEGRADED for s in services.values()):
            status = Health.DEGRADED
        else:
            status = Health.UP

        return ServiceHealth(status=status, services=services)
