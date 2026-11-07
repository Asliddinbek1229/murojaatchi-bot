from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject


class IsSuperAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, is_super: bool = False) -> bool:
        return is_super


class IsNotSuperAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, is_super: bool = False) -> bool:
        return not is_super


class IsAdmin(BaseFilter):
    """Shu botning faol admini yoki superadmin."""

    async def __call__(self, event: TelegramObject, is_admin: bool = False) -> bool:
        return is_admin


class IsMainBot(BaseFilter):
    async def __call__(self, event: TelegramObject, is_main: bool = True) -> bool:
        return is_main


class IsDeptBot(BaseFilter):
    async def __call__(self, event: TelegramObject, is_main: bool = True) -> bool:
        return not is_main
