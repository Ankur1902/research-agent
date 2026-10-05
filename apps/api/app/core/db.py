from app.core.config import settings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings().database_url, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)


async def db():
    async with Session() as session:
        yield session
