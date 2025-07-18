"""
Modèles pour les signaux de trading générés par l'IA.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List
from pydantic import BaseModel, Field, validator
from sqlalchemy import Column, String, Float, DateTime, Enum as SQLEnum, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.utils.database import Base


class SignalType(str, Enum):
    """Types de signaux de trading."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE = "CLOSE"


class SignalStrength(str, Enum):
    """Force du signal."""
    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"
    VERY_STRONG = "VERY_STRONG"


class RiskLevel(str, Enum):
    """Niveau de risque."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class SignalStatus(str, Enum):
    """Statut du signal."""
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


# Modèle SQLAlchemy
class Signal(Base):
    """Signal de trading en base de données."""
    __tablename__ = "signals"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Identifiants
    ticker = Column(String(20), nullable=False, index=True)
    exchange = Column(String(50))
    
    # Signal
    signal_type = Column(SQLEnum(SignalType), nullable=False)
    signal_strength = Column(SQLEnum(SignalStrength), nullable=False)
    confidence_score = Column('confidence', Float, nullable=False)  # 0.0 à 1.0
    
    # Prix et quantités
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float)
    quantity = Column(Float)
    position_size_percent = Column(Float)  # % du capital
    
    # Risk Management
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    risk_reward_ratio = Column(Float)
    max_loss_amount = Column(Float)
    risk_level = Column(SQLEnum(RiskLevel))
    
    # Timing
    valid_until = Column(DateTime)
    execution_deadline = Column(DateTime)
    
    # Statut
    status = Column(SQLEnum(SignalStatus), default=SignalStatus.PENDING)
    executed_at = Column(DateTime)
    execution_price = Column(Float)
    
    # Analyse
    technical_indicators = Column(JSON)
    sentiment_score = Column(Float)
    market_conditions = Column(JSON)
    reasoning = Column(String(1000))
    
    # Méta
    model_version = Column(String(50))
    model_confidence_scores = Column(JSON)
    extra_metadata = Column('metadata', JSON)


# Modèles Pydantic pour l'API
class RiskParameters(BaseModel):
    """Paramètres de gestion du risque."""
    max_position_size: float = Field(0.02, description="Taille max position (% du capital)")
    max_risk_per_trade: float = Field(0.01, description="Risque max par trade (% du capital)")
    stop_loss_percent: float = Field(0.02, description="Stop loss par défaut (%)")
    take_profit_percent: float = Field(0.05, description="Take profit par défaut (%)")
    max_daily_trades: int = Field(10, description="Nombre max de trades par jour")
    max_open_positions: int = Field(5, description="Nombre max de positions ouvertes")
    max_correlation: float = Field(0.7, description="Corrélation max entre positions")
    
    @validator('max_position_size', 'max_risk_per_trade')
    def validate_percentages(cls, v):
        if not 0 < v <= 0.1:  # Max 10%
            raise ValueError("Les pourcentages doivent être entre 0 et 10%")
        return v


class SignalRequest(BaseModel):
    """Requête pour générer un signal."""
    ticker: str
    exchange: Optional[str] = None
    timeframe: str = "1h"
    risk_parameters: Optional[RiskParameters] = None
    include_reasoning: bool = True


class SignalResponse(BaseModel):
    """Réponse avec signal généré."""
    id: str
    timestamp: datetime
    ticker: str
    exchange: Optional[str]
    
    signal_type: SignalType
    signal_strength: SignalStrength
    confidence_score: float = Field(..., ge=0, le=1)
    
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size_percent: float
    risk_reward_ratio: float
    
    risk_level: RiskLevel
    valid_until: datetime
    
    technical_summary: Optional[Dict] = None
    sentiment_score: Optional[float] = None
    reasoning: Optional[str] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SignalBatch(BaseModel):
    """Batch de signaux pour traitement en masse."""
    signals: List[SignalResponse]
    generated_at: datetime
    model_version: str
    market_overview: Optional[Dict] = None


class SignalPerformance(BaseModel):
    """Métriques de performance d'un signal."""
    signal_id: str
    ticker: str
    signal_type: SignalType
    
    entry_price: float
    exit_price: Optional[float]
    current_price: float
    
    pnl: float
    pnl_percent: float
    status: SignalStatus
    
    timestamp: datetime
    executed_at: Optional[datetime]
    closed_at: Optional[datetime]
    
    hit_stop_loss: bool = False
    hit_take_profit: bool = False
    
    holding_period_hours: Optional[float]
    max_drawdown: Optional[float]
    risk_reward_achieved: Optional[float]


class SignalValidation(BaseModel):
    """Validation d'un signal avant exécution."""
    signal_id: str
    is_valid: bool
    validation_errors: List[str] = []
    
    # Checks
    risk_check_passed: bool
    position_size_check_passed: bool
    correlation_check_passed: bool
    market_hours_check_passed: bool
    liquidity_check_passed: bool
    
    # Ajustements suggérés
    adjusted_position_size: Optional[float]
    adjusted_stop_loss: Optional[float]
    adjusted_take_profit: Optional[float]
    
    warnings: List[str] = []
    recommendations: List[str] = []


class MarketContext(BaseModel):
    """Contexte de marché pour la génération de signaux."""
    timestamp: datetime
    
    # Indices majeurs
    sp500_trend: str  # "BULLISH", "BEARISH", "NEUTRAL"
    vix_level: float
    dollar_index: float
    
    # Breadth
    advance_decline_ratio: float
    new_highs_lows: Dict[str, int]
    
    # Sentiment
    fear_greed_index: int
    put_call_ratio: float
    
    # Liquidité
    market_volume: Dict[str, float]
    
    # Événements
    upcoming_events: List[Dict]
    recent_news_sentiment: float
