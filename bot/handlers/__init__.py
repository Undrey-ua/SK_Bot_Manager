from aiogram import Router

from bot.handlers import clients, start, visit


def setup_routers() -> Router:
    root = Router()
    root.include_router(start.router)
    root.include_router(clients.router)
    root.include_router(visit.router)
    return root
