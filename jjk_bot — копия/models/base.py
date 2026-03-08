from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Создаем движок для SQLite
engine = create_async_engine("sqlite+aiosqlite:///jujutsu_bot.db", echo=False)

async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    """Инициализация базы данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)