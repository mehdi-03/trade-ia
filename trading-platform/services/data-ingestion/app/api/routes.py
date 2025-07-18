"""
Routes API pour le service d'ingestion de données.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.database import get_db_session, get_tsdb_session
from app.models.market_data import (
    MarketData, CryptoData, NewsArticle, 
    TechnicalIndicator, SentimentData
)

logger = structlog.get_logger()
router = APIRouter()


# Modèles Pydantic pour les réponses
class MarketDataResponse(BaseModel):
    ticker: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    bid: Optional[float]
    ask: Optional[float]


class CryptoDataResponse(BaseModel):
    exchange: str
    symbol: str
    timestamp: datetime
    last: float
    bid: float
    ask: float
    volume: float
    change_24h: Optional[float]
    change_percentage_24h: Optional[float]


class TechnicalIndicatorsResponse(BaseModel):
    ticker: str
    timestamp: datetime
    timeframe: str
    rsi: Optional[float]
    macd: Optional[float]
    sma_50: Optional[float]
    sma_200: Optional[float]
    indicators: Dict


class NewsResponse(BaseModel):
    id: str
    source: str
    category: str
    title: str
    description: Optional[str]
    url: Optional[str]
    published_at: datetime
    sentiment_score: Optional[float]
    sentiment_label: Optional[str]


class SentimentResponse(BaseModel):
    target: str
    timestamp: datetime
    sentiment_score: float
    positive_count: int
    negative_count: int
    neutral_count: int
    period: str


# Routes pour les données de marché
@router.get("/market-data/{ticker}")
async def get_market_data(
    ticker: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(100, le=1000),
    session: AsyncSession = Depends(get_tsdb_session)
) -> List[MarketDataResponse]:
    """Récupère les données de marché pour un ticker."""
    try:
        query = select(MarketData).where(MarketData.ticker == ticker)
        
        if start:
            query = query.where(MarketData.timestamp >= start)
        if end:
            query = query.where(MarketData.timestamp <= end)
            
        query = query.order_by(MarketData.timestamp.desc()).limit(limit)
        
        result = await session.execute(query)
        data = result.scalars().all()
        
        return [
            MarketDataResponse(
                ticker=d.ticker,
                timestamp=d.timestamp,
                open=d.open_price,
                high=d.high_price,
                low=d.low_price,
                close=d.close_price,
                volume=d.volume,
                bid=d.bid,
                ask=d.ask
            )
            for d in data
        ]
        
    except Exception as e:
        logger.error(f"Erreur récupération market data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Routes pour les données crypto
@router.get("/crypto-data/{exchange}/{symbol}")
async def get_crypto_data(
    exchange: str,
    symbol: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(100, le=1000),
    session: AsyncSession = Depends(get_tsdb_session)
) -> List[CryptoDataResponse]:
    """Récupère les données crypto pour une paire sur un exchange."""
    try:
        # Remplacer / par _ dans le symbol pour l'URL
        symbol = symbol.replace("_", "/")
        
        query = select(CryptoData).where(
            and_(
                CryptoData.exchange == exchange,
                CryptoData.symbol == symbol
            )
        )
        
        if start:
            query = query.where(CryptoData.timestamp >= start)
        if end:
            query = query.where(CryptoData.timestamp <= end)
            
        query = query.order_by(CryptoData.timestamp.desc()).limit(limit)
        
        result = await session.execute(query)
        data = result.scalars().all()
        
        return [
            CryptoDataResponse(
                exchange=d.exchange,
                symbol=d.symbol,
                timestamp=d.timestamp,
                last=d.last,
                bid=d.bid,
                ask=d.ask,
                volume=d.volume,
                change_24h=d.change_24h,
                change_percentage_24h=d.change_percentage_24h
            )
            for d in data
        ]
        
    except Exception as e:
        logger.error(f"Erreur récupération crypto data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Routes pour les indicateurs techniques
@router.get("/indicators/{ticker}")
async def get_technical_indicators(
    ticker: str,
    timeframe: str = Query("1h", regex="^(1m|5m|15m|1h|4h|1d)$"),
    exchange: Optional[str] = None,
    limit: int = Query(50, le=500),
    session: AsyncSession = Depends(get_tsdb_session)
) -> List[TechnicalIndicatorsResponse]:
    """Récupère les indicateurs techniques calculés."""
    try:
        query = select(TechnicalIndicator).where(
            and_(
                TechnicalIndicator.ticker == ticker,
                TechnicalIndicator.timeframe == timeframe
            )
        )
        
        if exchange:
            query = query.where(TechnicalIndicator.exchange == exchange)
            
        query = query.order_by(TechnicalIndicator.timestamp.desc()).limit(limit)
        
        result = await session.execute(query)
        data = result.scalars().all()
        
        return [
            TechnicalIndicatorsResponse(
                ticker=d.ticker,
                timestamp=d.timestamp,
                timeframe=d.timeframe,
                rsi=d.rsi,
                macd=d.macd,
                sma_50=d.sma_50,
                sma_200=d.sma_200,
                indicators={
                    "sma": {
                        "10": d.sma_10,
                        "20": d.sma_20,
                        "50": d.sma_50,
                        "200": d.sma_200
                    },
                    "ema": {
                        "10": d.ema_10,
                        "20": d.ema_20,
                        "50": d.ema_50
                    },
                    "momentum": {
                        "rsi": d.rsi,
                        "macd": d.macd,
                        "macd_signal": d.macd_signal,
                        "macd_histogram": d.macd_histogram
                    },
                    "volatility": {
                        "bollinger_upper": d.bollinger_upper,
                        "bollinger_middle": d.bollinger_middle,
                        "bollinger_lower": d.bollinger_lower,
                        "atr": d.atr
                    },
                    "trend": {
                        "adx": d.adx
                    },
                    "oscillators": {
                        "stochastic_k": d.stochastic_k,
                        "stochastic_d": d.stochastic_d
                    },
                    "volume": {
                        "volume_sma": d.volume_sma,
                        "obv": d.obv
                    }
                }
            )
            for d in data
        ]
        
    except Exception as e:
        logger.error(f"Erreur récupération indicateurs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Routes pour les news et sentiment
@router.get("/news")
async def get_news(
    category: Optional[str] = None,
    sentiment: Optional[str] = Query(None, regex="^(positive|negative|neutral)$"),
    hours: int = Query(24, le=168),  # Max 7 jours
    limit: int = Query(50, le=200),
    session: AsyncSession = Depends(get_db_session)
) -> List[NewsResponse]:
    """Récupère les dernières news avec leur sentiment."""
    try:
        since = datetime.now() - timedelta(hours=hours)
        query = select(NewsArticle).where(NewsArticle.published_at >= since)
        
        if category:
            query = query.where(NewsArticle.category == category)
        if sentiment:
            query = query.where(NewsArticle.sentiment_label == sentiment)
            
        query = query.order_by(NewsArticle.published_at.desc()).limit(limit)
        
        result = await session.execute(query)
        articles = result.scalars().all()
        
        return [
            NewsResponse(
                id=str(article.id),
                source=article.source,
                category=article.category,
                title=article.title,
                description=article.description,
                url=article.url,
                published_at=article.published_at,
                sentiment_score=article.sentiment_score,
                sentiment_label=article.sentiment_label
            )
            for article in articles
        ]
        
    except Exception as e:
        logger.error(f"Erreur récupération news: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sentiment/{target}")
async def get_sentiment(
    target: str,
    period: str = Query("1h", regex="^(1h|4h|1d|1w)$"),
    limit: int = Query(24, le=168),
    session: AsyncSession = Depends(get_db_session)
) -> List[SentimentResponse]:
    """Récupère l'historique du sentiment pour un ticker/catégorie."""
    try:
        query = select(SentimentData).where(
            and_(
                SentimentData.target == target,
                SentimentData.period == period
            )
        ).order_by(SentimentData.timestamp.desc()).limit(limit)
        
        result = await session.execute(query)
        sentiments = result.scalars().all()
        
        return [
            SentimentResponse(
                target=s.target,
                timestamp=s.timestamp,
                sentiment_score=s.sentiment_score,
                positive_count=s.positive_count,
                negative_count=s.negative_count,
                neutral_count=s.neutral_count,
                period=s.period
            )
            for s in sentiments
        ]
        
    except Exception as e:
        logger.error(f"Erreur récupération sentiment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Routes d'agrégation
@router.get("/stats/overview")
async def get_stats_overview(
    session: AsyncSession = Depends(get_db_session)
) -> Dict:
    """Récupère les statistiques globales du système."""
    try:
        # Comptage des enregistrements
        market_count = await session.scalar(
            select(func.count(MarketData.id))
        )
        crypto_count = await session.scalar(
            select(func.count(CryptoData.id))
        )
        news_count = await session.scalar(
            select(func.count(NewsArticle.id))
        )
        
        # Dernières mises à jour
        last_market = await session.scalar(
            select(func.max(MarketData.timestamp))
        )
        last_crypto = await session.scalar(
            select(func.max(CryptoData.timestamp))
        )
        
        return {
            "records": {
                "market_data": market_count,
                "crypto_data": crypto_count,
                "news_articles": news_count
            },
            "last_updates": {
                "market_data": last_market,
                "crypto_data": last_crypto
            },
            "status": "operational"
        }
        
    except Exception as e:
        logger.error(f"Erreur stats overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket endpoint pour les données temps réel
@router.websocket("/ws/stream")
async def websocket_stream(websocket):
    """WebSocket pour streaming des données temps réel."""
    await websocket.accept()
    
    try:
        # TODO: Implémenter le streaming depuis RabbitMQ
        while True:
            data = await websocket.receive_text()
            # Echo pour test
            await websocket.send_text(f"Echo: {data}")
            
    except Exception as e:
        logger.error(f"Erreur WebSocket: {e}")
    finally:
        await websocket.close()