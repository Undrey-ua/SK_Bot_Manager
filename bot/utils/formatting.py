from __future__ import annotations

from database.models import VISIT_TYPE_LABELS, Client, Stand, VisitType
from visit_task_labels import visit_task_label
from web.client_geo import client_display_city, client_display_comment


def user_first_name(full_name: str) -> str:
    """Перше слово з ПІБ — для привітань («Андрій Вовнянко» → «Андрій»)."""
    parts = full_name.strip().split()
    return parts[0] if parts else full_name.strip()


def stand_names(client: Client) -> list[str]:
    return [link.stand.name for link in client.stand_links if link.stand.is_active]


def format_client_card(client: Client) -> str:
    stands = ", ".join(stand_names(client)) or "—"
    region_name = client.region.name if client.region else "—"
    title = f"<b>{client.name}</b>"
    if client.is_potential:
        title = f"⭐ {title}\n<i>Потенційний клієнт</i>"
    return (
        f"{title}\n\n"
        f"Область: {region_name}\n"
        f"Адреса: {client.address}\n"
        f"Місто: {client_display_city(client)}\n"
        f"Коментар: {client_display_comment(client)}\n"
        f"Стенди: {stands}"
    )


def format_visit_saved(
    *,
    visit_id: int,
    client_name: str,
    visit_type: str,
    tasks: list[str],
    comment: str | None,
    photo_count: int,
) -> str:
    visit_label = VISIT_TYPE_LABELS[VisitType(visit_type)]
    tasks_text = (
        ", ".join(visit_task_label(t) for t in tasks) if tasks else "—"
    )
    comment_text = comment.strip() if comment else "—"
    photos_text = f"{photo_count} шт." if photo_count else "—"
    return (
        f"✅ <b>Візит #{visit_id} збережено</b>\n\n"
        f"Клієнт: {client_name}\n"
        f"Тип: {visit_label}\n"
        f"Задачі: {tasks_text}\n"
        f"Коментар: {comment_text}\n"
        f"Фото: {photos_text}"
    )


def format_stand_list(stands: list[Stand], *, active_only: bool = True) -> str:
    items = [s for s in stands if s.is_active or not active_only]
    if not items:
        return "—"
    return "\n".join(f"• {s.name}" + ("" if s.is_active else " (вимк.)") for s in items)
