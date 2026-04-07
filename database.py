import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from models import Base, User, Match, Bet
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db():
    logger.info("Initializing database and creating tables...")
    try:
        async with engine.begin() as conn:
            # Check connection
            await conn.execute(text("SELECT 1"))
            # Create tables
            await conn.run_sync(Base.metadata.create_all)
            logger.info("SQLAlchemy metadata creation executed.")
        
        # Dispose and recreate engine to ensure all changes are flushed
        # (Sometimes necessary for certain PostgreSQL setups)
        await engine.dispose()
        logger.info("Database initialization complete.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
