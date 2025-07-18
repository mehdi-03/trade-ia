"""
Tests d'intégration pour le pipeline data-ingestion → ai-engine → signal publishing.
"""

import sys
import os
import pytest
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch, AsyncMock

# Ensure the service package is discoverable when running tests from repo root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.ia_engine import IAEngine
from app.models.signals import Signal, SignalType, SignalStrength
from app.utils.message_queue import MessageQueue


class TestDataIngestionToAIEngineFlow:
    """Tests du flux data-ingestion → ai-engine."""
    
    @pytest.fixture
    def sample_market_data(self):
        """Données de marché simulées."""
        return {
            "ticker": "AAPL",
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
    def ai_engine(self):
        """Instance du moteur IA pour les tests."""
        return IAEngine()
    
    @pytest.mark.asyncio
    async def test_market_data_consumption(self, ai_engine, sample_market_data):
        """Test de consommation des données de marché."""
        # Mock du message queue
        mock_message_queue = Mock()
        mock_message_queue.consume = AsyncMock()
        ai_engine.message_queue = mock_message_queue
        
        # Mock du DeepSeek client
        mock_deepseek = Mock()
        mock_deepseek.predict_signals = AsyncMock(return_value=[
            Signal(
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
        ])
        ai_engine.deepseek_client = mock_deepseek
        
        # Mock du risk manager
        mock_risk_manager = Mock()
        mock_risk_manager.validate_signal = AsyncMock(return_value=Mock(is_valid=True))
        ai_engine.risk_manager = mock_risk_manager
        
        # Test de traitement des données de marché
        await ai_engine._process_market_data(sample_market_data)
        
        # Vérifications
        mock_deepseek.predict_signals.assert_called_once()
        mock_risk_manager.validate_signal.assert_called_once()
        
        # Vérification que les données sont normalisées correctement
        call_args = mock_deepseek.predict_signals.call_args[0][0]
        assert call_args["ticker"] == "AAPL"
        assert "technical_indicators" in call_args
        assert "market_context" in call_args
    
    @pytest.mark.asyncio
    async def test_signal_validation_and_publishing(self, ai_engine):
        """Test de validation et publication des signaux."""
        # Signal de test
        test_signal = Signal(
            id="test_signal_002",
            ticker="GOOGL",
            signal_type=SignalType.SELL,
            signal_strength=SignalStrength.MODERATE,
            confidence_score=0.75,
            entry_price=2800.0,
            stop_loss=2850.0,
            take_profit=2750.0,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Mock du message queue
        mock_message_queue = Mock()
        mock_message_queue.publish = AsyncMock()
        ai_engine.message_queue = mock_message_queue
        
        # Mock du risk manager avec validation réussie
        mock_risk_manager = Mock()
        mock_validation = Mock(
            is_valid=True,
            validation_errors=[],
            warnings=[],
            recommendations=["Signal validé"]
        )
        mock_risk_manager.validate_signal = AsyncMock(return_value=mock_validation)
        ai_engine.risk_manager = mock_risk_manager
        
        # Test de traitement du signal
        await ai_engine._process_signal(test_signal)
        
        # Vérifications
        mock_risk_manager.validate_signal.assert_called_once()
        mock_message_queue.publish.assert_called_once()
        
        # Vérification du contenu du message publié
        publish_call = mock_message_queue.publish.call_args
        assert publish_call[1]["exchange"] == "trading_signals"
        assert publish_call[1]["routing_key"] == "signals.validated"
        
        message_body = json.loads(publish_call[0][0])
        assert message_body["ticker"] == "GOOGL"
        assert message_body["signal_type"] == "SELL"
    
    @pytest.mark.asyncio
    async def test_signal_rejection_on_validation_failure(self, ai_engine):
        """Test de rejet des signaux invalides."""
        test_signal = Signal(
            id="test_signal_003",
            ticker="TSLA",
            signal_type=SignalType.BUY,
            signal_strength=SignalStrength.STRONG,
            confidence_score=0.90,
            entry_price=800.0,
            stop_loss=750.0,
            take_profit=900.0,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Mock du message queue
        mock_message_queue = Mock()
        mock_message_queue.publish = AsyncMock()
        ai_engine.message_queue = mock_message_queue
        
        # Mock du risk manager avec validation échouée
        mock_risk_manager = Mock()
        mock_validation = Mock(
            is_valid=False,
            validation_errors=["Risk too high", "Insufficient liquidity"],
            warnings=[],
            recommendations=[]
        )
        mock_risk_manager.validate_signal = AsyncMock(return_value=mock_validation)
        ai_engine.risk_manager = mock_risk_manager
        
        # Test de traitement du signal
        await ai_engine._process_signal(test_signal)
        
        # Vérifications
        mock_risk_manager.validate_signal.assert_called_once()
        
        # Le signal ne doit pas être publié
        mock_message_queue.publish.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_duplicate_signal_prevention(self, ai_engine):
        """Test de prévention des signaux dupliqués."""
        test_signal = Signal(
            id="test_signal_004",
            ticker="MSFT",
            signal_type=SignalType.BUY,
            signal_strength=SignalStrength.STRONG,
            confidence_score=0.85,
            entry_price=300.0,
            stop_loss=290.0,
            take_profit=320.0,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Ajout du signal au cache
        cache_key = f"{test_signal.ticker}_{test_signal.signal_type}_{test_signal.timestamp.date()}"
        ai_engine.signal_cache[cache_key] = test_signal
        
        # Mock du message queue
        mock_message_queue = Mock()
        mock_message_queue.publish = AsyncMock()
        ai_engine.message_queue = mock_message_queue
        
        # Test de traitement du signal dupliqué
        await ai_engine._process_signal(test_signal)
        
        # Le signal ne doit pas être publié car déjà en cache
        mock_message_queue.publish.assert_not_called()


class TestMessageQueueCompatibility:
    """Tests de compatibilité des message queues."""
    
    @pytest.mark.asyncio
    async def test_market_data_queue_format(self):
        """Test du format des messages sur la queue market_data."""
        # Format attendu par data-ingestion
        expected_format = {
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
                "bollinger_bands": "lower"
            }
        }
        
        # Vérification que le format est JSON-sérialisable
        json_str = json.dumps(expected_format)
        deserialized = json.loads(json_str)
        
        assert deserialized["ticker"] == "AAPL"
        assert "technical_indicators" in deserialized
        assert "timestamp" in deserialized
    
    @pytest.mark.asyncio
    async def test_signal_queue_format(self):
        """Test du format des messages sur la queue trading_signals."""
        # Format attendu par order-executor
        expected_format = {
            "id": "signal_001",
            "ticker": "AAPL",
            "signal_type": "BUY",
            "signal_strength": "STRONG",
            "confidence_score": 0.85,
            "entry_price": 151.2,
            "stop_loss": 148.0,
            "take_profit": 155.0,
            "timestamp": "2024-01-15T10:30:00Z",
            "validation": {
                "is_valid": True,
                "validation_errors": [],
                "warnings": [],
                "recommendations": ["Signal validé"]
            }
        }
        
        # Vérification que le format est JSON-sérialisable
        json_str = json.dumps(expected_format)
        deserialized = json.loads(json_str)
        
        assert deserialized["ticker"] == "AAPL"
        assert deserialized["signal_type"] == "BUY"
        assert "validation" in deserialized


class TestEndToEndPipeline:
    """Tests end-to-end du pipeline complet."""
    
    @pytest.mark.asyncio
    async def test_complete_pipeline_simulation(self):
        """Simulation du pipeline complet."""
        # 1. Données de marché simulées
        market_data = {
            "ticker": "AAPL",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "open": 150.0,
            "high": 152.5,
            "low": 149.8,
            "close": 151.2,
            "volume": 1500000,
            "technical_indicators": {
                "rsi": 35.2,
                "macd": 0.15,
                "bollinger_bands": "lower",
                "atr": 2.5
            }
        }
        
        # 2. Moteur IA avec mocks
        ai_engine = IAEngine()
        
        # Mock du DeepSeek client
        mock_deepseek = Mock()
        mock_deepseek.predict_signals = AsyncMock(return_value=[
            Signal(
                id="e2e_signal_001",
                ticker="AAPL",
                signal_type=SignalType.BUY,
                signal_strength=SignalStrength.STRONG,
                confidence_score=0.85,
                entry_price=151.2,
                stop_loss=148.0,
                take_profit=155.0,
                timestamp=datetime.now(timezone.utc)
            )
        ])
        ai_engine.deepseek_client = mock_deepseek
        
        # Mock du risk manager
        mock_risk_manager = Mock()
        mock_validation = Mock(
            is_valid=True,
            validation_errors=[],
            warnings=[],
            recommendations=["Signal validé"]
        )
        mock_risk_manager.validate_signal = AsyncMock(return_value=mock_validation)
        ai_engine.risk_manager = mock_risk_manager
        
        # Mock du message queue
        mock_message_queue = Mock()
        mock_message_queue.publish = AsyncMock()
        ai_engine.message_queue = mock_message_queue
        
        # 3. Exécution du pipeline
        await ai_engine._process_market_data(market_data)
        
        # 4. Vérifications
        # DeepSeek a été appelé
        mock_deepseek.predict_signals.assert_called_once()
        
        # Risk manager a été appelé
        mock_risk_manager.validate_signal.assert_called_once()
        
        # Signal a été publié
        mock_message_queue.publish.assert_called_once()
        
        # Vérification du contenu du message final
        publish_call = mock_message_queue.publish.call_args
        message_body = json.loads(publish_call[0][0])
        
        assert message_body["ticker"] == "AAPL"
        assert message_body["signal_type"] == "BUY"
        assert message_body["confidence_score"] == 0.85
        assert "validation" in message_body
