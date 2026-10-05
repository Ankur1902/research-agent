from fastapi import HTTPException
from sqlalchemy import select


async def owned(session, model, resource_id: str, organization_id: str):
    value = await session.scalar(select(model).where(model.id == resource_id, model.organization_id == organization_id))
    if value is None:
        raise HTTPException(404, "Resource not found")
    return value


def serialize(entity):
    return {column.name: getattr(entity, column.name) for column in entity.__table__.columns}
