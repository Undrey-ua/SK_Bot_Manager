from __future__ import annotations

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from web.auth import WebUser, get_web_user, require_auth_redirect


async def get_db_session():
    from web.app import container

    async with container.session_factory() as session:
        yield session


async def require_web_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> WebUser:
    redirect = require_auth_redirect(request)
    if redirect is not None:
        from fastapi import HTTPException

        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return await get_web_user(request, session)
