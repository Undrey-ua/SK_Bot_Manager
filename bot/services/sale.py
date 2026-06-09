from __future__ import annotations

from datetime import date
from decimal import Decimal

from database.models import Sale
from database.repositories.sale import SaleRepository


class SaleService:
    def __init__(self, repo: SaleRepository) -> None:
        self._repo = repo

    async def create(
        self,
        *,
        manager_id: int,
        client_id: int,
        brand_id: int,
        quantity: Decimal,
        sold_at: date | None = None,
        comment: str | None = None,
    ) -> Sale:
        return await self._repo.create(
            manager_id=manager_id,
            client_id=client_id,
            brand_id=brand_id,
            quantity=quantity,
            sold_at=sold_at or date.today(),
            comment=comment,
        )
