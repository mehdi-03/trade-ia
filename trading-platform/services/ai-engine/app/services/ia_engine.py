"""
Moteur principal d'IA pour la génération de signaux de trading.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import structlog
from sqlalchemy import select, and_
import json

from app.utils.deepseek_client import DeepSeekClient
from app.utils.message_queue import MessageQueue
from app.utils.database import get_db_session, get_tsdb_session
from app.models.signals import (
    Signal, SignalType, SignalStrength, RiskLevel, 
    SignalStatus, RiskParameters, SignalResponse
)
from app.utils.risk_manager import RiskManager
from app.utils.metrics import (
    signal_generation_counter, signal_validation_counter,
    ai_processing_duration, model_inference_duration
)

logger = structlog.get_logger()


class IAEngine:
    """Moteur principal pour la génération de signaux via DeepSeek."""
    
    def __init__(self):
        self.is_running = False
        self.deepseek_client = None
        self.message_queue = None
        self.risk_manager = None
        
        # Configuration
        self.processing_interval = 60  # secondes
        self.tickers_to_watch = []
        self.model_version = "deepseek-v3-trading-1.0"
        
        # Cache pour éviter les signaux répétitifs
        self.signal_cache = {}
        self.cache_ttl = 300  # 5 minutes
        
    async def initialize(self):
        """Initialise tous les composants du moteur."""
        try:
            logger.info("Initialisation du moteur IA...")
            
            # Initialisation DeepSeek
            self.deepseek_client = DeepSeekClient()
            await self.deepseek_client.connect()
            
            # Initialisation Message Queue
            self.message_queue = MessageQueue()
            await self.message_queue.connect()
            
            # Initialisation Risk Manager
            self.risk_manager = RiskManager()
            await self.risk_manager.initialize()
            
            # Chargement des tickers à surveiller
            await self._load_tickers()
            
            logger.info("Moteur IA initialisé avec succès")
            
        except Exception as e:
            logger.error(f"Erreur initialisation moteur IA: {e}")
            raise
    
    async def _load_tickers(self):
        """Charge la liste des tickers actifs depuis la base de données."""
        async with get_db_session() as session:
            try:
                # TODO: Requête pour charger les tickers actifs
                # Pour l'instant, liste statique
                self.tickers_to_watch = [
                    {"ticker": "BTC/USDT", "exchange": "binance"},
                    {"ticker": "ETH/USDT", "exchange": "binance"},
                    {"ticker": "AAPL", "exchange": None},
                    {"ticker": "TSLA", "exchange": None},
                    {"ticker": "SPY", "exchange": None},
                ]
                
                logger.info(f"Chargé {len(self.tickers_to_watch)} tickers")
                
            except Exception as e:
                logger.error(f"Erreur chargement tickers: {e}")
    
    async def process_market_data(self, message: Dict, _):
        """Traite les messages de données de marché reçus."""
        try:
            with ai_processing_duration.labels(operation="market_data_processing").time():
                data_type = message.get("type")
                data = message.get("data")
                
                if not data:
                    return
                
                # Extraction des informations
                ticker = data.get("ticker") or data.get("symbol")
                exchange = data.get("exchange")
                
                if not ticker:
                    return
                
                # Vérification si le ticker est surveillé
                if not self._is_watched_ticker(ticker, exchange):
                    return
                
                # Collecte des données pour analyse
                timeseries_data = await self._collect_timeseries_data(ticker, exchange)
                
                if not timeseries_data:
                    logger.warning(f"Pas de données suffisantes pour {ticker}")
                    return
                
                # Contexte de marché
                market_context = await self._get_market_context()
                
                # Génération de signaux via DeepSeek
                with model_inference_duration.labels(model="deepseek-v3").time():
                    signals = await self.deepseek_client.predict_signals(
                        timeseries_data,
                        market_context
                    )
                
                # Traitement des signaux générés
                for signal_data in signals:
                    await self._process_signal(signal_data, ticker, exchange)
                    
        except Exception as e:
            logger.error(f"Erreur traitement données marché: {e}")
    
    def _is_watched_ticker(self, ticker: str, exchange: Optional[str]) -> bool:
        """Vérifie si un ticker est dans la liste de surveillance."""
        for watched in self.tickers_to_watch:
            if watched["ticker"] == ticker:
                if exchange is None or watched["exchange"] == exchange:
                    return True
        return False
    
    async def _collect_timeseries_data(
        self, 
        ticker: str, 
        exchange: Optional[str]
    ) -> Dict[str, pd.DataFrame]:
        """Collecte les données historiques pour différents timeframes."""
        timeseries_data = {}
        
        async with get_tsdb_session() as session:
            try:
                timeframes = ["1m", "5m", "15m", "1h", "4h"]
                
                for timeframe in timeframes:
                    # Calcul de la période de lookback
                    lookback = self._get_lookback_period(timeframe)
                    start_time = datetime.now() - lookback
                    
                    # Construction de la requête
                    if exchange:  # Crypto
                        from services.data_ingestion.app.models.market_data import CryptoData
                        query = select(CryptoData).where(
                            and_(
                                CryptoData.symbol == ticker,
                                CryptoData.exchange == exchange,
                                CryptoData.timestamp >= start_time
                            )
                        ).order_by(CryptoData.timestamp)
                    else:  # Stocks
                        from services.data_ingestion.app.models.market_data import MarketData
                        query = select(MarketData).where(
                            and_(
                                MarketData.ticker == ticker,
                                MarketData.timestamp >= start_time
                            )
                        ).order_by(MarketData.timestamp)
                    
                    result = await session.execute(query)
                    rows = result.scalars().all()
                    
                    if rows and len(rows) > 50:
                        # Conversion en DataFrame
                        df = pd.DataFrame([
                            {
                                "timestamp": row.timestamp,
                                "open": row.open_price,
                                "high": row.high_price,
                                "low": row.low_price,
                                "close": row.close_price if hasattr(row, 'close_price') else row.last,
                                "volume": row.volume,
                            }
                            for row in rows
                        ])
                        
                        df.set_index("timestamp", inplace=True)
                        
                        # Ajout des indicateurs techniques depuis la DB
                        df = await self._enrich_with_indicators(df, ticker, timeframe, session)
                        
                        timeseries_data[timeframe] = df
                        
                return timeseries_data
                
            except Exception as e:
                logger.error(f"Erreur collecte données {ticker}: {e}")
                return {}
    
    def _get_lookback_period(self, timeframe: str) -> timedelta:
        """Retourne la période de lookback pour un timeframe."""
        lookback_map = {
            "1m": timedelta(hours=4),
            "5m": timedelta(hours=12),
            "15m": timedelta(days=1),
            "1h": timedelta(days=7),
            "4h": timedelta(days=30),
            "1d": timedelta(days=180),
        }
        return lookback_map.get(timeframe, timedelta(days=7))
    
    async def _enrich_with_indicators(
        self, 
        df: pd.DataFrame, 
        ticker: str, 
        timeframe: str,
        session
    ) -> pd.DataFrame:
        """Enrichit le DataFrame avec les indicateurs techniques."""
        try:
            from services.data_ingestion.app.models.market_data import TechnicalIndicator
            
            # Requête des indicateurs
            query = select(TechnicalIndicator).where(
                and_(
                    TechnicalIndicator.ticker == ticker,
                    TechnicalIndicator.timeframe == timeframe,
                    TechnicalIndicator.timestamp >= df.index[0]
                )
            ).order_by(TechnicalIndicator.timestamp)
            
            result = await session.execute(query)
            indicators = result.scalars().all()
            
            # Ajout au DataFrame
            for ind in indicators:
                if ind.timestamp in df.index:
                    df.loc[ind.timestamp, 'rsi'] = ind.rsi
                    df.loc[ind.timestamp, 'macd'] = ind.macd
                    df.loc[ind.timestamp, 'sma_50'] = ind.sma_50
                    df.loc[ind.timestamp, 'sma_200'] = ind.sma_200
                    df.loc[ind.timestamp, 'atr'] = ind.atr
                    df.loc[ind.timestamp, 'adx'] = ind.adx
            
            return df
            
        except Exception as e:
            logger.error(f"Erreur enrichissement indicateurs: {e}")
            return df
    
    async def _get_market_context(self) -> Dict:
        """Récupère le contexte global du marché."""
        try:
            # TODO: Implémenter la récupération du contexte réel
            # Pour l'instant, contexte simulé
            
            return {
                "timestamp": datetime.now(),
                "sp500_trend": "NEUTRAL",
                "vix_level": 18.5,
                "dollar_index": 104.2,
                "advance_decline_ratio": 1.2,
                "new_highs_lows": {"highs": 150, "lows": 75},
                "fear_greed_index": 55,
                "put_call_ratio": 0.95,
                "market_volume": {"NYSE": 4.5e9, "NASDAQ": 5.2e9},
                "upcoming_events": [],
                "recent_news_sentiment": 0.15
            }
            
        except Exception as e:
            logger.error(f"Erreur récupération contexte marché: {e}")
            return {}
    
    async def _process_signal(
        self, 
        signal_data: Dict, 
        ticker: str, 
        exchange: Optional[str]
    ):
        """Traite et valide un signal généré."""
        try:
            # Vérification du cache
            cache_key = f"{ticker}:{exchange}:{signal_data['signal_type']}"
            if self._is_signal_cached(cache_key):
                logger.info(f"Signal déjà généré récemment pour {ticker}")
                return
            
            # Enrichissement du signal
            signal_data["ticker"] = ticker
            signal_data["exchange"] = exchange
            signal_data["model_version"] = self.model_version
            
            # Validation par le gestionnaire de risque
            risk_params = RiskParameters()  # Params par défaut
            validated_signal = await self.risk_manager.validate_signal(
                signal_data, 
                risk_params
            )
            
            if not validated_signal["is_valid"]:
                logger.warning(
                    f"Signal rejeté pour {ticker}: {validated_signal['validation_errors']}"
                )
                signal_validation_counter.labels(
                    ticker=ticker, 
                    status="rejected"
                ).inc()
                return
            
            # Ajustements si nécessaire
            if validated_signal.get("adjusted_position_size"):
                signal_data["position_size_percent"] = validated_signal["adjusted_position_size"]
            if validated_signal.get("adjusted_stop_loss"):
                signal_data["stop_loss"] = validated_signal["adjusted_stop_loss"]
            if validated_signal.get("adjusted_take_profit"):
                signal_data["take_profit"] = validated_signal["adjusted_take_profit"]
            
            # Détermination du niveau de risque
            signal_data["risk_level"] = self._calculate_risk_level(signal_data)
            
            # Sauvegarde en base de données
            saved_signal = await self._save_signal(signal_data)
            
            if saved_signal:
                # Publication dans la queue
                await self._publish_signal(saved_signal)
                
                # Mise à jour du cache
                self._cache_signal(cache_key)
                
                # Métriques
                signal_generation_counter.labels(
                    ticker=ticker,
                    signal_type=signal_data["signal_type"],
                    strength=signal_data.get("signal_strength", "MODERATE")
                ).inc()
                
                signal_validation_counter.labels(
                    ticker=ticker,
                    status="validated"
                ).inc()
                
                logger.info(
                    f"Signal généré et publié: {ticker} {signal_data['signal_type']} "
                    f"@ {signal_data['entry_price']}"
                )
                
        except Exception as e:
            logger.error(f"Erreur traitement signal: {e}")
    
    def _is_signal_cached(self, cache_key: str) -> bool:
        """Vérifie si un signal similaire a été généré récemment."""
        if cache_key in self.signal_cache:
            cached_time = self.signal_cache[cache_key]
            if datetime.now() - cached_time < timedelta(seconds=self.cache_ttl):
                return True
        return False
    
    def _cache_signal(self, cache_key: str):
        """Met en cache un signal généré."""
        self.signal_cache[cache_key] = datetime.now()
        
        # Nettoyage du cache expiré
        current_time = datetime.now()
        expired_keys = [
            k for k, v in self.signal_cache.items()
            if current_time - v > timedelta(seconds=self.cache_ttl)
        ]
        for key in expired_keys:
            del self.signal_cache[key]
    
    def _calculate_risk_level(self, signal_data: Dict) -> str:
        """Calcule le niveau de risque d'un signal."""
        risk_score = 0
        
        # Position size
        pos_size = signal_data.get("position_size_percent", 0)
        if pos_size > 0.05:
            risk_score += 3
        elif pos_size > 0.03:
            risk_score += 2
        else:
            risk_score += 1
        
        # Risk/Reward ratio
        rr_ratio = signal_data.get("risk_reward_ratio", 0)
        if rr_ratio < 1.5:
            risk_score += 2
        elif rr_ratio > 3:
            risk_score -= 1
        
        # Volatilité
        if "technical_indicators" in signal_data:
            volatility = signal_data["technical_indicators"].get("volatility", 0)
            if volatility > 0.03:
                risk_score += 2
        
        # Détermination du niveau
        if risk_score >= 5:
            return RiskLevel.VERY_HIGH
        elif risk_score >= 4:
            return RiskLevel.HIGH
        elif risk_score >= 2:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    async def _save_signal(self, signal_data: Dict) -> Optional[Signal]:
        """Sauvegarde un signal en base de données."""
        async with get_db_session() as session:
            try:
                # Mappage du type de signal
                signal_type_map = {
                    "BUY": SignalType.BUY,
                    "STRONG_BUY": SignalType.BUY,
                    "SELL": SignalType.SELL,
                    "STRONG_SELL": SignalType.SELL,
                }
                
                # Mappage de la force du signal
                strength_map = {
                    "STRONG_BUY": SignalStrength.VERY_STRONG,
                    "BUY": SignalStrength.STRONG,
                    "SELL": SignalStrength.STRONG,
                    "STRONG_SELL": SignalStrength.VERY_STRONG,
                }
                
                signal = Signal(
                    ticker=signal_data["ticker"],
                    exchange=signal_data.get("exchange"),
                    signal_type=signal_type_map.get(signal_data["signal_type"], SignalType.HOLD),
                    signal_strength=strength_map.get(signal_data["signal_type"], SignalStrength.MODERATE),
                    confidence=signal_data["confidence"],
                    entry_price=signal_data["entry_price"],
                    stop_loss=signal_data["stop_loss"],
                    take_profit=signal_data["take_profit"],
                    position_size_percent=signal_data.get("position_size_percent", 0.02),
                    risk_reward_ratio=signal_data["risk_reward_ratio"],
                    risk_level=signal_data.get("risk_level", RiskLevel.MEDIUM),
                    valid_until=datetime.now() + timedelta(hours=4),
                    technical_indicators=signal_data.get("technical_indicators", {}),
                    sentiment_score=signal_data.get("sentiment_score"),
                    reasoning=signal_data.get("reasoning", ""),
                    model_version=self.model_version,
                    model_confidence_scores={
                        "score": signal_data.get("score", 0),
                        "confidence": signal_data["confidence"]
                    }
                )
                
                session.add(signal)
                await session.commit()
                
                return signal
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Erreur sauvegarde signal: {e}")
                return None
    
    async def _publish_signal(self, signal: Signal):
        """Publie un signal dans la message queue."""
        try:
            # Conversion en format de réponse
            signal_response = SignalResponse(
                id=str(signal.id),
                created_at=signal.created_at,
                ticker=signal.ticker,
                exchange=signal.exchange,
                signal_type=signal.signal_type,
                signal_strength=signal.signal_strength,
                confidence=signal.confidence,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                position_size_percent=signal.position_size_percent,
                risk_reward_ratio=signal.risk_reward_ratio,
                risk_level=signal.risk_level,
                valid_until=signal.valid_until,
                technical_summary=signal.technical_indicators,
                sentiment_score=signal.sentiment_score,
                reasoning=signal.reasoning
            )
            
            # Publication
            await self.message_queue.publish(
                exchange="trading_signals",
                routing_key=f"signal.{signal.ticker.replace('/', '_')}",
                message={
                    "type": "trading_signal",
                    "signal": signal_response.dict(),
                    "timestamp": datetime.now().isoformat()
                },
                priority=2 if signal.signal_strength == SignalStrength.VERY_STRONG else 1
            )
            
        except Exception as e:
            logger.error(f"Erreur publication signal: {e}")
    
    async def batch_process_tickers(self):
        """Traite tous les tickers surveillés en batch."""
        for ticker_info in self.tickers_to_watch:
            try:
                ticker = ticker_info["ticker"]
                exchange = ticker_info["exchange"]
                
                # Collecte des données
                timeseries_data = await self._collect_timeseries_data(ticker, exchange)
                
                if not timeseries_data:
                    continue
                
                # Contexte de marché
                market_context = await self._get_market_context()
                
                # Génération de signaux
                signals = await self.deepseek_client.predict_signals(
                    timeseries_data,
                    market_context
                )
                
                # Traitement des signaux
                for signal_data in signals:
                    await self._process_signal(signal_data, ticker, exchange)
                    
                # Pause entre tickers
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Erreur batch processing {ticker}: {e}")
    
    async def start(self):
        """Démarre le moteur IA."""
        self.is_running = True
        logger.info("Démarrage du moteur IA")
        
        try:
            # Initialisation
            await self.initialize()
            
            # Souscription aux messages de données de marché
            await self.message_queue.consume(
                queue_name="ai_processing",
                callback=self.process_market_data,
                exchange="market_data",
                routing_key="*.#"
            )
            
            # Boucle de traitement batch
            while self.is_running:
                try:
                    start_time = asyncio.get_event_loop().time()
                    
                    # Traitement batch périodique
                    await self.batch_process_tickers()
                    
                    # Maintien de l'intervalle
                    elapsed = asyncio.get_event_loop().time() - start_time
                    sleep_time = max(0, self.processing_interval - elapsed)
                    
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)
                        
                except Exception as e:
                    logger.error(f"Erreur boucle principale: {e}")
                    await asyncio.sleep(60)
                    
        except Exception as e:
            logger.error(f"Erreur fatale moteur IA: {e}")
            raise
        finally:
            await self.stop()
    
    async def stop(self):
        """Arrête le moteur IA."""
        self.is_running = False
        
        if self.deepseek_client:
            await self.deepseek_client.close()
            
        if self.message_queue:
            await self.message_queue.close()

        logger.info("Moteur IA arrêté")
