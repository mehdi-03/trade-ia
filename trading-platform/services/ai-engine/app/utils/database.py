"""
Utilitaires pour la gestion de la base de données.
"""

import os
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
import structlog
from app.models.signals import Base

logger = structlog.get_logger()

# Configuration de la base de données
DATABASE_URL = (
    f"postgresql+asyncpg://{os.getenv('DB_USER', 'trading')}:"
    f"{os.getenv('DB_PASSWORD', 'trading123')}@"
    f"{os.getenv('DB_HOST', 'localhost')}:"
    f"{os.getenv('DB_PORT', '5432')}/"
    f"{os.getenv('DB_NAME', 'trading_platform')}"
)

TIMESCALE_URL = (
    f"postgresql+asyncpg://{os.getenv('TSDB_USER', 'tsdb')}:"
    f"{os.getenv('TSDB_PASSWORD', 'tsdb123')}@"
    f"{os.getenv('TSDB_HOST', 'localhost')}:"
    f"{os.getenv('TSDB_PORT', '5433')}/"
    f"{os.getenv('TSDB_NAME', 'trading_timeseries')}"
)

# Engines
engine = None
tsdb_engine = None

# Session factories
async_session = None
async_tsdb_session = None


async def init_db():
    """Initialise les connexions aux bases de données."""
    global engine, tsdb_engine, async_session, async_tsdb_session
    
    try:
        # Base de données principale
        engine = create_async_engine(
            DATABASE_URL,
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
            poolclass=NullPool,
        )
        
        # TimescaleDB
        tsdb_engine = create_async_engine(
            TIMESCALE_URL,
            echo=False,
            poolclass=NullPool,
        )
        
        # Session factories
        async_session = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        async_tsdb_session = async_sessionmaker(
            tsdb_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        # Création des tables si elles n'existent pas
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
        logger.info("Bases de données initialisées avec succès")
        
    except Exception as e:
        logger.error(f"Erreur initialisation DB: {e}")
        raise


@asynccontextmanager
async def get_db_session():
    """Context manager pour obtenir une session de base de données."""
    if not async_session:
        await init_db()
        
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_tsdb_session():
    """Context manager pour obtenir une session TimescaleDB."""
    if not async_tsdb_session:
        await init_db()
        
    async with async_tsdb_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db():
    """Ferme les connexions aux bases de données."""
    global engine, tsdb_engine
    
    if engine:
        await engine.dispose()
        engine = None
        
    if tsdb_engine:
        await tsdb_engine.dispose()
        tsdb_engine = None
        
    logger.info("Connexions DB fermées") 
