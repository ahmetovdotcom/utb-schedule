from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Асинхронный engine
engine = create_async_engine(
    settings.DATABASE_URL_ASYNC,
    echo=False,  # Логирование SQL-запросов (отключить в продакшене)
    future=True,
)

# Фабрика сессий
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Базовый класс для всех моделей ORM."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection для получения асинхронной сессии БД."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
