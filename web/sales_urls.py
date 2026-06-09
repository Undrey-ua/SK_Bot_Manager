from __future__ import annotations

from urllib.parse import urlencode


def analytics_sales_return_url(query: dict[str, str]) -> str:
    params = {"section": "sales"}
    for key in (
        "period_kind",
        "year",
        "month",
        "quarter",
        "manager_id",
        "region_id",
        "city",
        "stand_id",
        "brand_id",
    ):
        value = query.get(key)
        if value:
            params[key] = value
    return f"/analytics?{urlencode(params)}"
