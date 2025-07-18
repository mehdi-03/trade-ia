"""
Modèles de données pour le service d'ingestion.
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Integer, DateTime, Boolean, 
    Text, JSON, Index, ForeignKey, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

Base = declarative_base()


class Ticker(Base):
    """Modèle pour les tickers surveillés."""
    __tablename__ = "tickers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), unique=True, nullable=False)
    name = Column(String(100))
    exchange = Column(String(50))
    asset_type = Column(String(20))  # stock, crypto, forex, commodity
    sector = Column(String(50))
    industry = Column(String(50))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    market_data = relationship("MarketData", back_populates="ticker_ref")


class MarketData(Base):
    """Données de marché (stocks, ETFs, etc.)."""
    __tablename__ = "market_data"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker_id = Column(UUID(as_uuid=True), ForeignKey("tickers.id"))
    ticker = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # Prix OHLCV
    open_price = Column(Float)
    high_price = Column(Float)
    low_price = Column(Float)
    close_price = Column(Float)
    volume = Column(Integer)
    
    # Bid/Ask
    bid = Column(Float)
    ask = Column(Float)
    bid_size = Column(Integer)
    ask_size = Column(Integer)
    
    # Métadonnées
    metadata = Column(JSON)  # market_cap, pe_ratio, etc.
    
    # Relations
    ticker_ref = relationship("Ticker", back_populates="market_data")
    
    # Index pour requêtes temporelles
    __table_args__ = (
        Index("idx_market_data_ticker_timestamp", "ticker", "timestamp"),
    )


class CryptoData(Base):
    """Données crypto multi-exchange."""
    __tablename__ = "crypto_data"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exchange = Column(String(50), nullable=False)
    symbol = Column(String(20), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    
    # Prix
    bid = Column(Float)
    ask = Column(Float)
    last = Column(Float)
    open_price = Column(Float)
    high_price = Column(Float)
    low_price = Column(Float)
    close_price = Column(Float)
    
    # Volumes
    volume = Column(Float)
    quote_volume = Column(Float)
    
    # Indicateurs
    vwap = Column(Float)
    change_24h = Column(Float)
    change_percentage_24h = Column(Float)
    
    # Orderbook snapshot
    orderbook_data = Column(JSON)
    
    # Index composites
    __table_args__ = (
        Index("idx_crypto_exchange_symbol_timestamp", "exchange", "symbol", "timestamp"),
        UniqueConstraint("exchange", "symbol", "timestamp", name="uq_crypto_data"),
    )


class Exchange(Base):
    """Informations sur les exchanges crypto."""
    __tablename__ = "exchanges"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False)
    display_name = Column(String(100))
    is_active = Column(Boolean, default=True)
    supported_markets = Column(JSON)  # ["spot", "futures", "options"]
    api_rate_limit = Column(Integer, default=1000)
    metadata = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


class NewsArticle(Base):
    """Articles de news et analyses."""
    __tablename__ = "news_articles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(50), nullable=False)  # newsapi, twitter, rss_*
    category = Column(String(50))  # crypto, stocks, forex, etc.
    
    # Contenu
    title = Column(String(500), nullable=False)
    description = Column(Text)
    content = Column(Text)
    url = Column(String(1000), unique=True)
    author = Column(String(200))
    
    # Dates
    published_at = Column(DateTime, nullable=False)
    collected_at = Column(DateTime, default=datetime.utcnow)
    
    # Sentiment
    sentiment_score = Column(Float)  # -1 à 1
    sentiment_label = Column(String(20))  # positive, negative, neutral
    sentiment_confidence = Column(Float)  # 0 à 1
    
    # Métadonnées
    metadata = Column(JSON)
    
    # Index
    __table_args__ = (
        Index("idx_news_category_published", "category", "published_at"),
        Index("idx_news_sentiment", "sentiment_label", "published_at"),
    )


class SentimentData(Base):
    """Données de sentiment agrégées."""
    __tablename__ = "sentiment_data"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target = Column(String(50), nullable=False)  # ticker, category, etc.
    target_type = Column(String(20), nullable=False)  # ticker, category, sector
    timestamp = Column(DateTime, nullable=False)
    
    # Métriques agrégées
    sentiment_score = Column(Float)  # Score moyen
    positive_count = Column(Integer, default=0)
    negative_count = Column(Integer, default=0)
    neutral_count = Column(Integer, default=0)
    total_count = Column(Integer, default=0)
    
    # Sources
    sources = Column(JSON)  # {"newsapi": 10, "twitter": 50, ...}
    
    # Période d'agrégation
    period = Column(String(20))  # 1h, 4h, 1d, 1w
    
    # Index
    __table_args__ = (
        Index("idx_sentiment_target_timestamp", "target", "timestamp"),
        UniqueConstraint("target", "target_type", "timestamp", "period", name="uq_sentiment"),
    )


class TechnicalIndicator(Base):
    """Indicateurs techniques calculés."""
    __tablename__ = "technical_indicators"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(20), nullable=False)
    exchange = Column(String(50))
    timestamp = Column(DateTime, nullable=False)
    timeframe = Column(String(10), nullable=False)  # 1m, 5m, 1h, 1d
    
    # Moyennes mobiles
    sma_10 = Column(Float)
    sma_20 = Column(Float)
    sma_50 = Column(Float)
    sma_200 = Column(Float)
    ema_10 = Column(Float)
    ema_20 = Column(Float)
    ema_50 = Column(Float)
    
    # Indicateurs
    rsi = Column(Float)
    macd = Column(Float)
    macd_signal = Column(Float)
    macd_histogram = Column(Float)
    bollinger_upper = Column(Float)
    bollinger_middle = Column(Float)
    bollinger_lower = Column(Float)
    atr = Column(Float)
    adx = Column(Float)
    stochastic_k = Column(Float)
    stochastic_d = Column(Float)
    
    # Volume
    volume_sma = Column(Float)
    obv = Column(Float)
    
    # Index
    __table_args__ = (
        Index("idx_indicators_ticker_timeframe_timestamp", "ticker", "timeframe", "timestamp"),
    )
