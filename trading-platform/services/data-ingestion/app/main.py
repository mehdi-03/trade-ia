"""
Service d'ingestion de données pour la plateforme de trading.
Collecte les données de marché, news et sentiment en temps réel.
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
import structlog
from dotenv import load_dotenv
import os

from app.collectors.market_data import MarketDataCollector
from app.collectors.news_collector import NewsCollector
from app.collectors.crypto_collector import CryptoCollector
from app.processors.data_pipeline import DataPipeline
from app.utils.database import init_db, get_db_session
from app.utils.message_queue import MessageQueue
from app.api import routes

# Configuration du logging
logger = structlog.get_logger()

# Chargement des variables d'environnement
load_dotenv()

# Initialisation des collecteurs globaux
market_collector = None
news_collector = None
crypto_collector = None
data_pipeline = None
message_queue = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application."""
    global market_collector, news_collector, crypto_collector, data_pipeline, message_queue
    
    logger.info("Démarrage du service d'ingestion de données...")
    
    # Initialisation de la base de données
    await init_db()
    
    # Initialisation de la message queue
    message_queue = MessageQueue()
    await message_queue.connect()
    
    # Initialisation des collecteurs
    market_collector = MarketDataCollector()
    news_collector = NewsCollector()
    crypto_collector = CryptoCollector()
    
    # Initialisation du pipeline de traitement
    data_pipeline = DataPipeline(message_queue)
    
    # Démarrage des tâches de collecte en arrière-plan
    asyncio.create_task(market_collector.start_collection())
    asyncio.create_task(news_collector.start_collection())
    asyncio.create_task(crypto_collector.start_collection())
    asyncio.create_task(data_pipeline.start_processing())
    
    logger.info("Service d'ingestion démarré avec succès")
    
    yield
    
    # Nettoyage
    logger.info("Arrêt du service d'ingestion...")
    if market_collector:
        await market_collector.stop()
    if news_collector:
        await news_collector.stop()
    if crypto_collector:
        await crypto_collector.stop()
    if data_pipeline:
        await data_pipeline.stop()
    if message_queue:
        await message_queue.close()


# Création de l'application FastAPI
app = FastAPI(
    title="Service d'Ingestion de Données",
    description="Collecte et traitement des données de marché en temps réel",
    version="1.0.0",
    lifespan=lifespan
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclusion des routes
app.include_router(routes.router, prefix="/api/v1")

# Exposition des métriques Prometheus
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/health")
async def health_check():
    """Vérification de l'état du service."""
    return {
        "status": "healthy",
        "service": "data-ingestion",
        "collectors": {
            "market": market_collector.is_running if market_collector else False,
            "news": news_collector.is_running if news_collector else False,
            "crypto": crypto_collector.is_running if crypto_collector else False,
        },
        "pipeline": data_pipeline.is_running if data_pipeline else False,
    }


@app.get("/")
async def root():
    """Point d'entrée principal."""
    return {
        "service": "Data Ingestion Service",
        "version": "1.0.0",
        "status": "running"
    }