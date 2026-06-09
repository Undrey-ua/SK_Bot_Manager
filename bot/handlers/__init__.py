from aiogram import Router

from bot.handlers import admin_stands, client_form, clients, regions, reserves, sale, start, tasks, visit


def setup_routers() -> Router:
    root = Router()
    root.include_router(start.router)
    root.include_router(clients.router)
    root.include_router(client_form.router)
    root.include_router(regions.router)
    root.include_router(admin_stands.router)
    root.include_router(visit.router)
    root.include_router(sale.router)
    root.include_router(reserves.router)
    root.include_router(tasks.router)
    return root
