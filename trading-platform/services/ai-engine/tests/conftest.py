"""
Configuration pytest pour les tests du service AI Engine.
"""

import pytest
import asyncio
import os
from unittest.mock import Mock, AsyncMock
from app.services.ia_engine import IAEngine
from app.utils.message_queue import MessageQueue
from app.utils.database import init_db


@pytest.fixture(scope="session")
def event_loop():
    """Crée une boucle d'événements pour les tests asynchrones."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def mock_ai_engine():
    """Instance du moteur IA avec tous les composants mockés."""
    engine = IAEngine()
    
    # Mock du DeepSeek client
    mock_deepseek = Mock()
    mock_deepseek.model_loaded = True
    mock_deepseek.predict_signals = AsyncMock()
    engine.deepseek_client = mock_deepseek
    
    # Mock du message queue
    mock_message_queue = Mock()
    mock_message_queue.connection = Mock()
    mock_message_queue.connection.is_open = True
    mock_message_queue.publish = AsyncMock()
    mock_message_queue.consume = AsyncMock()
    engine.message_queue = mock_message_queue
    
    # Mock du risk manager
    mock_risk_manager = Mock()
    mock_risk_manager.validate_signal = AsyncMock()
    engine.risk_manager = mock_risk_manager
    
    return engine


@pytest.fixture
def sample_market_data():
    """Données de marché simulées pour les tests."""
    return {
        "ticker": "AAPL",
        "timestamp": "2024-01-15T10:30:00Z",
        "open": 150.0,
        "high": 152.5,
        "low": 149.8,
        "close": 151.2,
        "volume": 1500000,
        "technical_indicators": {
            "rsi": 35.2,
            "macd": 0.15,
            "bollinger_bands": "lower",
            "atr": 2.5,
            "sma_20": 148.5,
            "sma_50": 145.2
        },
        "market_context": {
            "volatility": 0.02,
            "trend": "bullish",
            "support_level": 148.0,
            "resistance_level": 155.0
        }
    }


@pytest.fixture
def sample_signal():
    """Signal simulé pour les tests."""
    from app.models.signals import Signal, SignalType, SignalStrength
    from datetime import datetime, timezone
    
    return Signal(
        id="test_signal_001",
        ticker="AAPL",
        signal_type=SignalType.BUY,
        signal_strength=SignalStrength.STRONG,
        confidence_score=0.85,
        entry_price=151.2,
        stop_loss=148.0,
        take_profit=155.0,
        timestamp=datetime.now(timezone.utc)
    )


@pytest.fixture
async def mock_database():
    """Mock de la base de données."""
    # Mock de la session DB
    mock_session = Mock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    
    return mock_session


@pytest.fixture
def mock_config():
    """Configuration simulée pour les tests."""
    return {
        "model": {
            "path": "/models/deepseek-v3",
            "device": "cuda",
            "max_length": 2048,
            "temperature": 0.7
        },
        "thresholds": {
            "confidence_min": 0.7,
            "signal_strength_min": "MODERATE"
        },
        "risk_management": {
            "max_position_size": 0.05,
            "max_risk_per_trade": 0.02,
            "max_daily_trades": 10,
            "max_open_positions": 5
        }
    }


# Configuration des variables d'environnement pour les tests
@pytest.fixture(autouse=True)
def setup_test_env():
    """Configure l'environnement de test."""
    os.environ.update({
        "DB_HOST": "localhost",
        "DB_USER": "test_user",
        "DB_PASSWORD": "test_pass",
        "DB_NAME": "test_db",
        "RABBITMQ_HOST": "localhost",
        "RABBITMQ_USER": "test_user",
        "RABBITMQ_PASSWORD": "test_pass",
        "REDIS_HOST": "localhost",
        "REDIS_PASSWORD": "test_pass"
    }) 