"""
Service AI Engine pour la génération de signaux de trading.
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
import structlog
from dotenv import load_dotenv
import os

from app.services.ia_engine import IAEngine
from app.utils.database import init_db
from app.api import routes

# Configuration du logging
logger = structlog.get_logger()

# Chargement des variables d'environnement
load_dotenv()

# Instance globale du moteur IA
ai_engine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application."""
    global ai_engine
    
    logger.info("Démarrage du service AI Engine...")
    
    # Initialisation de la base de données
    await init_db()
    
    # Initialisation du moteur IA
    ai_engine = IAEngine()
    await ai_engine.initialize()
    
    # Démarrage du moteur en arrière-plan
    asyncio.create_task(ai_engine.start())
    
    logger.info("Service AI Engine démarré avec succès")
    
    yield
    
    # Nettoyage
    logger.info("Arrêt du service AI Engine...")
    if ai_engine:
        await ai_engine.stop()


# Création de l'application FastAPI
app = FastAPI(
    title="AI Engine Service",
    description="Service de génération de signaux de trading via DeepSeek",
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
    global ai_engine
    
    health_status = {
        "status": "healthy",
        "service": "ai-engine",
        "version": "1.0.0",
        "components": {
            "ai_engine": ai_engine.is_running if ai_engine else False,
            "deepseek_client": ai_engine.deepseek_client.model_loaded if ai_engine and ai_engine.deepseek_client else False,
            "message_queue": ai_engine.message_queue.connection.is_open if ai_engine and ai_engine.message_queue and ai_engine.message_queue.connection else False,
            "risk_manager": ai_engine.risk_manager is not None if ai_engine else False,
        }
    }
    
    # Vérification de la santé globale
    all_healthy = all(health_status["components"].values())
    health_status["status"] = "healthy" if all_healthy else "degraded"
    
    return health_status


@app.get("/")
async def root():
    """Point d'entrée principal."""
    return {
        "service": "AI Engine Service",
        "version": "1.0.0",
        "status": "running",
        "description": "Service de génération de signaux de trading via DeepSeek V3"
    }


@app.get("/status")
async def get_status():
    """Statut détaillé du service."""
    global ai_engine
    
    if not ai_engine:
        raise HTTPException(status_code=503, detail="AI Engine not initialized")
    
    return {
        "ai_engine": {
            "is_running": ai_engine.is_running,
            "tickers_watched": len(ai_engine.tickers_to_watch),
            "model_version": ai_engine.model_version,
            "cache_size": len(ai_engine.signal_cache),
        },
        "deepseek_client": {
            "model_loaded": ai_engine.deepseek_client.model_loaded if ai_engine.deepseek_client else False,
            "model_path": ai_engine.deepseek_client.model_path if ai_engine.deepseek_client else None,
            "device": ai_engine.deepseek_client.device if ai_engine.deepseek_client else None,
        },
        "message_queue": {
            "connected": ai_engine.message_queue.connection.is_open if ai_engine.message_queue and ai_engine.message_queue.connection else False,
            "exchanges": list(ai_engine.message_queue.exchanges.keys()) if ai_engine.message_queue else [],
        }
    } 
