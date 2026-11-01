"""A-SOUL collection: ICS live schedule with pre-live scene events, and dynamics-site queries with card delivery."""

from len_bot.plugin import Plugin, PluginContext

from .schedule import CalendarFeature
from .dynamics import DynamicsFeature
from .commands import DynamicsCommands


class Asoul(CalendarFeature, DynamicsFeature, DynamicsCommands, Plugin):
    def __init__(self, ctx: PluginContext) -> None:
        super().__init__(ctx)
        self._init_calendar(ctx)
        self._init_dynamics(ctx)

    async def stop(self) -> None:
        try:
            await self._stop_dynamics()
        finally:
            await self._stop_calendar()
