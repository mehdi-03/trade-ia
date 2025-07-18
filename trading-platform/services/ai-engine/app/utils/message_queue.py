"""
Gestion de la message queue (RabbitMQ).
"""

import os
import json
import asyncio
from typing import Dict, Any, Callable, Optional
import aio_pika
from aio_pika import ExchangeType
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()


class MessageQueue:
    """Gestionnaire de messages RabbitMQ."""
    
    def __init__(self):
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.Channel] = None
        self.exchanges: Dict[str, aio_pika.Exchange] = {}
        
        # Configuration
        self.rabbitmq_url = (
            f"amqp://{os.getenv('RABBITMQ_USER', 'rabbit')}:"
            f"{os.getenv('RABBITMQ_PASSWORD', 'rabbit123')}@"
            f"{os.getenv('RABBITMQ_HOST', 'localhost')}:"
            f"{os.getenv('RABBITMQ_PORT', '5672')}/"
        )
    
    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=60))
    async def connect(self):
        """Établit la connexion à RabbitMQ."""
        try:
            self.connection = await aio_pika.connect_robust(
                self.rabbitmq_url,
                loop=asyncio.get_event_loop()
            )
            
            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=10)
            
            # Déclaration des exchanges
            await self._declare_exchanges()
            
            logger.info("Connecté à RabbitMQ")
            
        except Exception as e:
            logger.error(f"Erreur connexion RabbitMQ: {e}")
            raise
    
    async def _declare_exchanges(self):
        """Déclare les exchanges nécessaires."""
        exchange_configs = {
            "market_data": ExchangeType.TOPIC,
            "trading_signals": ExchangeType.DIRECT,
            "orders": ExchangeType.DIRECT,
            "alerts": ExchangeType.FANOUT,
            "dlx": ExchangeType.TOPIC,  # Dead Letter Exchange
        }
        
        for name, exchange_type in exchange_configs.items():
            exchange = await self.channel.declare_exchange(
                name,
                exchange_type,
                durable=True
            )
            self.exchanges[name] = exchange
            
        logger.info("Exchanges déclarés")
    
    async def publish(
        self,
        exchange: str,
        routing_key: str,
        message: Dict[str, Any],
        priority: int = 0,
        expiration: Optional[int] = None
    ):
        """Publie un message dans un exchange."""
        if not self.channel:
            await self.connect()
            
        try:
            exchange_obj = self.exchanges.get(exchange)
            if not exchange_obj:
                logger.error(f"Exchange '{exchange}' non trouvé")
                return
                
            # Sérialisation du message
            body = json.dumps(message).encode()
            
            # Création du message avec propriétés
            message_obj = aio_pika.Message(
                body=body,
                content_type="application/json",
                priority=priority,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            
            if expiration:
                message_obj.expiration = expiration
            
            # Publication
            await exchange_obj.publish(
                message_obj,
                routing_key=routing_key
            )
            
            logger.debug(
                f"Message publié",
                exchange=exchange,
                routing_key=routing_key,
                size=len(body)
            )
            
        except Exception as e:
            logger.error(f"Erreur publication: {e}", exchange=exchange, routing_key=routing_key)
            raise
    
    async def consume(
        self,
        queue_name: str,
        callback: Callable,
        exchange: str,
        routing_key: str = "#",
        auto_ack: bool = False
    ):
        """Consomme des messages d'une queue."""
        if not self.channel:
            await self.connect()
            
        try:
            # Déclaration de la queue
            queue = await self.channel.declare_queue(
                queue_name,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": "dlx",
                    "x-message-ttl": 3600000,  # 1 heure
                }
            )
            
            # Binding à l'exchange
            exchange_obj = self.exchanges.get(exchange)
            if exchange_obj:
                await queue.bind(exchange_obj, routing_key)
            
            # Définition du callback wrapper
            async def process_message(message: aio_pika.IncomingMessage):
                async with message.process(ignore_processed=True):
                    try:
                        # Désérialisation
                        body = json.loads(message.body.decode())
                        
                        # Appel du callback
                        await callback(body, message)
                        
                        if not auto_ack:
                            await message.ack()
                            
                    except Exception as e:
                        logger.error(
                            f"Erreur traitement message: {e}",
                            queue=queue_name,
                            message_id=message.message_id
                        )
                        
                        if not auto_ack:
                            await message.nack(requeue=True)
            
            # Démarrage de la consommation
            await queue.consume(process_message, no_ack=auto_ack)
            
            logger.info(f"Consommation démarrée", queue=queue_name, exchange=exchange)
            
        except Exception as e:
            logger.error(f"Erreur consommation: {e}", queue=queue_name)
            raise
    
    async def close(self):
        """Ferme la connexion."""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            logger.info("Connexion RabbitMQ fermée")


# Instance singleton
_message_queue_instance = None


def get_message_queue() -> MessageQueue:
    """Retourne l'instance singleton de MessageQueue."""
    global _message_queue_instance
    if not _message_queue_instance:
        _message_queue_instance = MessageQueue()
    return _message_queue_instance 
