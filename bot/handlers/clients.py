from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards.inline import back_to_menu_keyboard, clients_keyboard
from bot.services.client import ClientService
from database.models import User

router = Router(name="clients")


@router.callback_query(F.data == "clients:list")
async def list_clients(
    callback: CallbackQuery,
    db_user: User,
    client_service: ClientService,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    clients = await client_service.list_by_manager(db_user.id)
    if not clients:
        await callback.message.edit_text(
            "📋 У вас поки немає клієнтів.\n"
            "Зверніться до адміністратора.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    lines = [f"• <b>{c.name}</b>" for c in clients]
    if any(c.district for c in clients):
        lines = []
        for c in clients:
            parts = [f"<b>{c.name}</b>"]
            if c.district:
                parts.append(c.district)
            if c.address:
                parts.append(c.address)
            lines.append(" • ".join(parts))

    await callback.message.edit_text(
        "📋 <b>Ваші клієнти</b>\n\n" + "\n".join(lines),
        reply_markup=back_to_menu_keyboard(),
    )
