"""
Collecteur de données crypto via CCXT.
Support de plus de 150 exchanges.
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Optional, Set
import ccxt.async_support as ccxt
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
import os

from app.utils.database import get_db_session
from app.models.market_data import CryptoData, Exchange
from app.utils.metrics import data_collection_counter, data_collection_errors
from app.utils.message_queue import MessageQueue

logger = structlog.get_logger()


class CryptoCollector:
    """Collecteur de données crypto multi-exchange."""
    
    def __init__(self):
        self.is_running = False
        self.collection_interval = int(os.getenv("CRYPTO_DATA_INTERVAL", "30"))  # secondes
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self.symbols: Set[str] = self._load_symbols()
        self.supported_exchanges = self._get_supported_exchanges()
        
    def _get_supported_exchanges(self) -> List[str]:
        """Retourne la liste des exchanges supportés."""
        # Top exchanges par volume
        return [
            "binance",
            "coinbase",
            "kraken",
            "bitfinex",
            "huobi",
            "okx",
            "bybit",
            "kucoin",
            "gateio",
            "bitstamp"
        ]
    
    def _load_symbols(self) -> Set[str]:
        """Charge la liste des paires à surveiller."""
        # TODO: Charger depuis la base de données
        default_symbols = {
            # Majors
            "BTC/USDT", "ETH/USDT", "BNB/USDT",
            # Alts populaires
            "SOL/USDT", "XRP/USDT", "ADA/USDT", "DOGE/USDT",
            "AVAX/USDT", "DOT/USDT", "MATIC/USDT", "LINK/USDT",
            "UNI/USDT", "ATOM/USDT", "LTC/USDT", "ETC/USDT",
            # Stablecoins
            "USDC/USDT", "BUSD/USDT", "DAI/USDT",
            # DeFi
            "AAVE/USDT", "SUSHI/USDT", "COMP/USDT", "CRV/USDT",
            # Paires BTC
            "ETH/BTC", "BNB/BTC", "SOL/BTC", "XRP/BTC"
        }
        return default_symbols
    
    async def initialize_exchanges(self):
        """Initialise les connexions aux exchanges."""
        for exchange_id in self.supported_exchanges:
            try:
                if exchange_id in ccxt.exchanges:
                    exchange_class = getattr(ccxt, exchange_id)
                    exchange = exchange_class({
                        'enableRateLimit': True,
                        'rateLimit': 1000,  # milliseconds
                        'options': {
                            'defaultType': 'spot',
                        }
                    })
                    
                    # Chargement des marchés
                    await exchange.load_markets()
                    self.exchanges[exchange_id] = exchange
                    logger.info(f"Exchange {exchange_id} initialisé")
                    
            except Exception as e:
                logger.error(f"Erreur initialisation {exchange_id}: {e}")
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_ticker(self, exchange: ccxt.Exchange, symbol: str) -> Optional[Dict]:
        """Récupère les données d'un ticker sur un exchange."""
        try:
            if symbol not in exchange.symbols:
                return None
                
            ticker = await exchange.fetch_ticker(symbol)
            orderbook = await exchange.fetch_order_book(symbol, limit=5)
            
            return {
                "exchange": exchange.id,
                "symbol": symbol,
                "timestamp": datetime.fromtimestamp(ticker['timestamp'] / 1000),
                "bid": ticker.get('bid', 0),
                "ask": ticker.get('ask', 0),
                "last": ticker.get('last', 0),
                "open": ticker.get('open', 0),
                "high": ticker.get('high', 0),
                "low": ticker.get('low', 0),
                "close": ticker.get('close', 0),
                "volume": ticker.get('baseVolume', 0),
                "quote_volume": ticker.get('quoteVolume', 0),
                "vwap": ticker.get('vwap', 0),
                "change": ticker.get('change', 0),
                "percentage": ticker.get('percentage', 0),
                "orderbook": {
                    "bids": [[float(price), float(amount)] for price, amount in orderbook['bids'][:5]],
                    "asks": [[float(price), float(amount)] for price, amount in orderbook['asks'][:5]],
                    "timestamp": orderbook['timestamp'],
                }
            }
            
        except Exception as e:
            logger.error(f"Erreur fetch {symbol} sur {exchange.id}: {e}")
            return None
    
    async def collect_exchange_data(self, exchange_id: str):
        """Collecte les données pour un exchange spécifique."""
        if exchange_id not in self.exchanges:
            return
            
        exchange = self.exchanges[exchange_id]
        tasks = []
        
        # Collecte parallèle pour tous les symboles
        for symbol in self.symbols:
            if symbol in exchange.symbols:
                task = asyncio.create_task(self.fetch_ticker(exchange, symbol))
                tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Traitement des résultats
        valid_data = []
        for result in results:
            if isinstance(result, dict) and result:
                valid_data.append(result)
                data_collection_counter.labels(
                    source="ccxt", 
                    ticker=f"{result['exchange']}:{result['symbol']}"
                ).inc()
        
        # Sauvegarde en base
        if valid_data:
            await self.save_crypto_data(valid_data)
            
        # Publication dans la message queue pour traitement temps réel
        if valid_data:
            await self.publish_to_queue(valid_data)
    
    async def save_crypto_data(self, data_list: List[Dict]):
        """Sauvegarde les données crypto dans TimescaleDB."""
        async with get_db_session() as session:
            try:
                for data in data_list:
                    crypto_data = CryptoData(
                        exchange=data["exchange"],
                        symbol=data["symbol"],
                        timestamp=data["timestamp"],
                        bid=data["bid"],
                        ask=data["ask"],
                        last=data["last"],
                        open_price=data["open"],
                        high_price=data["high"],
                        low_price=data["low"],
                        close_price=data["close"],
                        volume=data["volume"],
                        quote_volume=data["quote_volume"],
                        vwap=data.get("vwap"),
                        change_24h=data.get("change"),
                        change_percentage_24h=data.get("percentage"),
                        orderbook_data=data.get("orderbook"),
                    )
                    session.add(crypto_data)
                
                await session.commit()
                logger.info(f"Sauvegardé {len(data_list)} entrées crypto")
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Erreur sauvegarde crypto: {e}")
    
    async def publish_to_queue(self, data_list: List[Dict]):
        """Publie les données dans la message queue."""
        try:
            mq = MessageQueue()
            for data in data_list:
                await mq.publish(
                    exchange="market_data",
                    routing_key=f"crypto.{data['exchange']}.{data['symbol'].replace('/', '_')}",
                    message={
                        "type": "crypto_ticker",
                        "data": data,
                        "timestamp": datetime.now().isoformat()
                    }
                )
        except Exception as e:
            logger.error(f"Erreur publication queue: {e}")
    
    async def collect_all_exchanges(self):
        """Collecte les données de tous les exchanges."""
        tasks = []
        
        for exchange_id in self.exchanges.keys():
            task = asyncio.create_task(self.collect_exchange_data(exchange_id))
            tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def start_collection(self):
        """Démarre la collecte périodique."""
        self.is_running = True
        logger.info("Démarrage du collecteur crypto")
        
        # Initialisation des exchanges
        await self.initialize_exchanges()
        
        while self.is_running:
            try:
                start_time = asyncio.get_event_loop().time()
                
                await self.collect_all_exchanges()
                
                # Maintien de l'intervalle
                elapsed = asyncio.get_event_loop().time() - start_time
                sleep_time = max(0, self.collection_interval - elapsed)
                
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
            except Exception as e:
                logger.error(f"Erreur boucle crypto: {e}")
                await asyncio.sleep(30)
    
    async def stop(self):
        """Arrête la collecte et ferme les connexions."""
        self.is_running = False
        
        # Fermeture des exchanges
        for exchange in self.exchanges.values():
            try:
                await exchange.close()
            except:
                pass
                
        logger.info("Arrêt du collecteur crypto")