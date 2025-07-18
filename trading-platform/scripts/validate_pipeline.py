#!/usr/bin/env python3
"""
Script de validation end-to-end du pipeline de trading.
Teste le flux complet: data-ingestion → ai-engine → signal publishing
"""

import asyncio
import json
import time
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List
import aio_pika
import httpx
import structlog

logger = structlog.get_logger()

# Configuration
RABBITMQ_URL = "amqp://rabbit:rabbit123@localhost:5672/"
DATA_INGESTION_URL = "http://localhost:8001"
AI_ENGINE_URL = "http://localhost:8003"
API_GATEWAY_URL = "http://localhost:8000"

# Données de test
TEST_MARKET_DATA = {
    "type": "market_data",
    "data": {
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
}


class PipelineValidator:
    """Validateur du pipeline end-to-end."""
    
    def __init__(self):
        self.connection = None
        self.channel = None
        self.received_signals = []
        self.test_results = {}
        
    async def connect_rabbitmq(self):
        """Connexion à RabbitMQ."""
        try:
            self.connection = await aio_pika.connect_robust(RABBITMQ_URL)
            self.channel = await self.connection.channel()
            logger.info("Connecté à RabbitMQ")
        except Exception as e:
            logger.error(f"Erreur connexion RabbitMQ: {e}")
            raise
    
    async def check_service_health(self) -> Dict[str, bool]:
        """Vérifie la santé de tous les services."""
        health_status = {}
        
        async with httpx.AsyncClient() as client:
            # Vérification data-ingestion
            try:
                response = await client.get(f"{DATA_INGESTION_URL}/health", timeout=5)
                health_status["data_ingestion"] = response.status_code == 200
            except Exception as e:
                logger.error(f"Data-ingestion health check failed: {e}")
                health_status["data_ingestion"] = False
            
            # Vérification ai-engine
            try:
                response = await client.get(f"{AI_ENGINE_URL}/health", timeout=5)
                health_status["ai_engine"] = response.status_code == 200
            except Exception as e:
                logger.error(f"AI-engine health check failed: {e}")
                health_status["ai_engine"] = False
            
            # Vérification api-gateway
            try:
                response = await client.get(f"{API_GATEWAY_URL}/health", timeout=5)
                health_status["api_gateway"] = response.status_code == 200
            except Exception as e:
                logger.error(f"API-gateway health check failed: {e}")
                health_status["api_gateway"] = False
        
        return health_status
    
    async def publish_test_market_data(self):
        """Publie des données de marché de test."""
        try:
            exchange = await self.channel.declare_exchange(
                "market_data",
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            
            message = aio_pika.Message(
                body=json.dumps(TEST_MARKET_DATA).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )
            
            await exchange.publish(message, routing_key="market_data.stock")
            logger.info("Données de marché de test publiées")
            
        except Exception as e:
            logger.error(f"Erreur publication données test: {e}")
            raise
    
    async def listen_for_signals(self, timeout: int = 30):
        """Écoute les signaux générés."""
        try:
            queue = await self.channel.declare_queue(
                "test_signals_queue",
                durable=True
            )
            
            exchange = await self.channel.declare_exchange(
                "trading_signals",
                aio_pika.ExchangeType.DIRECT,
                durable=True
            )
            
            await queue.bind(exchange, "signals.validated")
            
            start_time = time.time()
            
            async def process_message(message: aio_pika.IncomingMessage):
                async with message.process():
                    try:
                        body = json.loads(message.body.decode())
                        self.received_signals.append(body)
                        logger.info(f"Signal reçu: {body.get('ticker')} {body.get('signal_type')}")
                    except Exception as e:
                        logger.error(f"Erreur traitement signal: {e}")
            
            # Écoute pendant le timeout
            await queue.consume(process_message, timeout=timeout)
            
        except Exception as e:
            logger.error(f"Erreur écoute signaux: {e}")
            raise
    
    async def validate_signal_format(self, signal: Dict[str, Any]) -> bool:
        """Valide le format d'un signal."""
        required_fields = [
            "id", "ticker", "signal_type", "signal_strength",
            "confidence_score", "entry_price", "stop_loss", "take_profit",
            "timestamp", "validation"
        ]
        
        for field in required_fields:
            if field not in signal:
                logger.error(f"Champ manquant dans le signal: {field}")
                return False
        
        # Validation des types
        if not isinstance(signal["confidence_score"], (int, float)):
            logger.error("confidence_score doit être un nombre")
            return False
        
        if signal["confidence_score"] < 0 or signal["confidence_score"] > 1:
            logger.error("confidence_score doit être entre 0 et 1")
            return False
        
        # Validation de la validation
        validation = signal.get("validation", {})
        if not isinstance(validation, dict):
            logger.error("validation doit être un objet")
            return False
        
        return True
    
    async def run_end_to_end_test(self) -> Dict[str, Any]:
        """Exécute le test end-to-end complet."""
        logger.info("Démarrage du test end-to-end")
        
        try:
            # 1. Vérification de la santé des services
            logger.info("Vérification de la santé des services...")
            health_status = await self.check_service_health()
            
            if not all(health_status.values()):
                logger.error("Certains services ne sont pas en bonne santé")
                for service, status in health_status.items():
                    logger.error(f"  {service}: {'OK' if status else 'KO'}")
                return {"success": False, "health_status": health_status}
            
            logger.info("Tous les services sont en bonne santé")
            
            # 2. Publication des données de test
            logger.info("Publication des données de marché de test...")
            await self.publish_test_market_data()
            
            # 3. Écoute des signaux générés
            logger.info("Écoute des signaux générés...")
            await self.listen_for_signals(timeout=30)
            
            # 4. Validation des résultats
            logger.info(f"Nombre de signaux reçus: {len(self.received_signals)}")
            
            if not self.received_signals:
                logger.error("Aucun signal généré")
                return {
                    "success": False,
                    "health_status": health_status,
                    "signals_received": 0,
                    "error": "Aucun signal généré"
                }
            
            # Validation du format de chaque signal
            valid_signals = 0
            for signal in self.received_signals:
                if await self.validate_signal_format(signal):
                    valid_signals += 1
                else:
                    logger.error(f"Signal invalide: {signal}")
            
            success = valid_signals == len(self.received_signals)
            
            return {
                "success": success,
                "health_status": health_status,
                "signals_received": len(self.received_signals),
                "valid_signals": valid_signals,
                "test_data": TEST_MARKET_DATA,
                "received_signals": self.received_signals
            }
            
        except Exception as e:
            logger.error(f"Erreur test end-to-end: {e}")
            return {"success": False, "error": str(e)}
    
    async def cleanup(self):
        """Nettoyage des ressources."""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()


async def main():
    """Fonction principale."""
    validator = PipelineValidator()
    
    try:
        await validator.connect_rabbitmq()
        results = await validator.run_end_to_end_test()
        
        # Affichage des résultats
        print("\n" + "="*50)
        print("RÉSULTATS DU TEST END-TO-END")
        print("="*50)
        
        if results["success"]:
            print("✅ Test réussi!")
            print(f"📊 Signaux reçus: {results['signals_received']}")
            print(f"✅ Signaux valides: {results['valid_signals']}")
            
            if results["received_signals"]:
                print("\n📈 Détail des signaux:")
                for i, signal in enumerate(results["received_signals"], 1):
                    print(f"  {i}. {signal['ticker']} - {signal['signal_type']} "
                          f"(confiance: {signal['confidence_score']:.2%})")
        else:
            print("❌ Test échoué!")
            if "error" in results:
                print(f"Erreur: {results['error']}")
            if "health_status" in results:
                print("\nÉtat des services:")
                for service, status in results["health_status"].items():
                    print(f"  {service}: {'✅' if status else '❌'}")
        
        print("="*50)
        
        # Code de sortie
        sys.exit(0 if results["success"] else 1)
        
    except Exception as e:
        logger.error(f"Erreur critique: {e}")
        print(f"❌ Erreur critique: {e}")
        sys.exit(1)
    finally:
        await validator.cleanup()


if __name__ == "__main__":
    asyncio.run(main()) 