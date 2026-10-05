import secrets
from datetime import timedelta

from app.core.config import settings
from app.core.db import db
from app.models.entities import LoginSession, Member, User, now
from app.security.guards import digest
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

hasher = PasswordHasher()


def verify_password(encoded: str, password: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except VerificationError:
        return False


async def principal(request: Request, session: AsyncSession = Depends(db)):
    token = request.cookies.get("researchos_session", "")
    login = await session.scalar(
        select(LoginSession).where(LoginSession.token_hash == digest(token), LoginSession.expires_at > now())
    )
    if not login:
        raise HTTPException(401, "Sign in to continue")
    member = await session.scalar(
        select(Member).where(Member.user_id == login.user_id, Member.organization_id == login.organization_id)
    )
    if not member:
        raise HTTPException(403, "Membership revoked")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("origin") != settings().public_origin or not secrets.compare_digest(
            request.headers.get("x-csrf-token", ""), login.csrf
        ):
            raise HTTPException(403, "Invalid request origin or CSRF token")
    user = await session.get(User, login.user_id)
    return {"user": user, "member": member, "session": login, "org": login.organization_id, "role": member.role}


async def issue_session(session, user, org, response):
    token = secrets.token_urlsafe(48)
    login = LoginSession(
        token_hash=digest(token),
        user_id=user.id,
        organization_id=org,
        csrf=secrets.token_urlsafe(32),
        expires_at=now() + timedelta(days=7),
    )
    session.add(login)
    await session.commit()
    response.set_cookie(
        "researchos_session",
        token,
        httponly=True,
        secure=settings().environment == "production",
        samesite="lax",
        max_age=604800,
        path="/",
    )
    return {"id": user.id, "name": user.name, "email": user.email, "csrf": login.csrf}
