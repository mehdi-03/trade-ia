"""
Pipeline de traitement des données collectées.
Calcul des indicateurs techniques et enrichissement.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
from ta import add_all_ta_features
from ta.utils import dropna
import structlog

from app.utils.database import get_tsdb_session
from app.utils.message_queue import MessageQueue
from app.models.market_data import TechnicalIndicator, MarketData, CryptoData
from app.utils.metrics import technical_indicator_calculation
from sqlalchemy import select, and_

logger = structlog.get_logger()


class DataPipeline:
    """Pipeline de traitement et enrichissement des données."""
    
    def __init__(self, message_queue: MessageQueue):
        self.is_running = False
        self.message_queue = message_queue
        self.processing_interval = 60  # secondes
        self.timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]
        
    async def calculate_technical_indicators(
        self, 
        ticker: str, 
        timeframe: str,
        exchange: Optional[str] = None
    ) -> Optional[Dict]:
        """Calcule les indicateurs techniques pour un ticker."""
        try:
            with technical_indicator_calculation.labels(
                indicator="all", 
                timeframe=timeframe
            ).time():
                # Récupération des données historiques
                df = await self._fetch_historical_data(ticker, timeframe, exchange)
                
                if df is None or len(df) < 50:
                    logger.warning(f"Données insuffisantes pour {ticker} {timeframe}")
                    return None
                
                # Nettoyage des données
                df = dropna(df)
                
                # Ajout de tous les indicateurs techniques
                df = add_all_ta_features(
                    df,
                    open="open",
                    high="high",
                    low="low",
                    close="close",
                    volume="volume",
                    fillna=True
                )
                
                # Extraction des dernières valeurs
                latest = df.iloc[-1]
                
                indicators = {
                    "ticker": ticker,
                    "exchange": exchange,
                    "timestamp": latest.name,
                    "timeframe": timeframe,
                    
                    # Moyennes mobiles
                    "sma_10": latest.get("trend_sma_fast", np.nan),
                    "sma_20": latest.get("trend_sma_slow", np.nan),
                    "sma_50": self._calculate_sma(df["close"], 50),
                    "sma_200": self._calculate_sma(df["close"], 200),
                    "ema_10": latest.get("trend_ema_fast", np.nan),
                    "ema_20": latest.get("trend_ema_slow", np.nan),
                    "ema_50": self._calculate_ema(df["close"], 50),
                    
                    # Momentum
                    "rsi": latest.get("momentum_rsi", np.nan),
                    "macd": latest.get("trend_macd", np.nan),
                    "macd_signal": latest.get("trend_macd_signal", np.nan),
                    "macd_histogram": latest.get("trend_macd_diff", np.nan),
                    
                    # Volatilité
                    "bollinger_upper": latest.get("volatility_bbh", np.nan),
                    "bollinger_middle": latest.get("volatility_bbm", np.nan),
                    "bollinger_lower": latest.get("volatility_bbl", np.nan),
                    "atr": latest.get("volatility_atr", np.nan),
                    
                    # Trend
                    "adx": latest.get("trend_adx", np.nan),
                    
                    # Oscillateurs
                    "stochastic_k": latest.get("momentum_stoch", np.nan),
                    "stochastic_d": latest.get("momentum_stoch_signal", np.nan),
                    
                    # Volume
                    "volume_sma": self._calculate_sma(df["volume"], 20),
                    "obv": latest.get("volume_obv", np.nan),
                }
                
                # Filtrage des NaN
                indicators = {k: v if not pd.isna(v) else None for k, v in indicators.items()}
                
                return indicators
                
        except Exception as e:
            logger.error(f"Erreur calcul indicateurs {ticker}: {e}")
            return None
    
    def _calculate_sma(self, series: pd.Series, period: int) -> float:
        """Calcule une moyenne mobile simple."""
        if len(series) < period:
            return np.nan
        return series.rolling(window=period).mean().iloc[-1]
    
    def _calculate_ema(self, series: pd.Series, period: int) -> float:
        """Calcule une moyenne mobile exponentielle."""
        if len(series) < period:
            return np.nan
        return series.ewm(span=period, adjust=False).mean().iloc[-1]
    
    async def _fetch_historical_data(
        self, 
        ticker: str, 
        timeframe: str,
        exchange: Optional[str] = None
    ) -> Optional[pd.DataFrame]:
        """Récupère les données historiques depuis TimescaleDB."""
        async with get_tsdb_session() as session:
            try:
                # Calcul de la période nécessaire
                period_map = {
                    "1m": timedelta(hours=4),
                    "5m": timedelta(hours=12),
                    "15m": timedelta(days=1),
                    "1h": timedelta(days=7),
                    "4h": timedelta(days=30),
                    "1d": timedelta(days=365),
                }
                
                start_time = datetime.now() - period_map.get(timeframe, timedelta(days=7))
                
                # Requête selon le type de données
                if exchange:  # Données crypto
                    query = select(CryptoData).where(
                        and_(
                            CryptoData.symbol == ticker,
                            CryptoData.exchange == exchange,
                            CryptoData.timestamp >= start_time
                        )
                    ).order_by(CryptoData.timestamp)
                else:  # Données stocks
                    query = select(MarketData).where(
                        and_(
                            MarketData.ticker == ticker,
                            MarketData.timestamp >= start_time
                        )
                    ).order_by(MarketData.timestamp)
                
                result = await session.execute(query)
                rows = result.scalars().all()
                
                if not rows:
                    return None
                
                # Conversion en DataFrame
                data = []
                for row in rows:
                    data.append({
                        "timestamp": row.timestamp,
                        "open": row.open_price,
                        "high": row.high_price,
                        "low": row.low_price,
                        "close": row.close_price if hasattr(row, 'close_price') else row.last,
                        "volume": row.volume,
                    })
                
                df = pd.DataFrame(data)
                df.set_index("timestamp", inplace=True)
                
                # Resampling selon le timeframe
                if timeframe != "1m":
                    df = df.resample(timeframe).agg({
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum"
                    }).dropna()
                
                return df
                
            except Exception as e:
                logger.error(f"Erreur fetch données historiques: {e}")
                return None
    
    async def save_technical_indicators(self, indicators: Dict):
        """Sauvegarde les indicateurs calculés."""
        async with get_tsdb_session() as session:
            try:
                technical = TechnicalIndicator(**indicators)
                session.add(technical)
                await session.commit()
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Erreur sauvegarde indicateurs: {e}")
    
    async def process_market_data_message(self, message: Dict, _):
        """Traite un message de données de marché."""
        try:
            data_type = message.get("type")
            data = message.get("data")
            
            if not data:
                return
            
            # Déclenchement du calcul d'indicateurs
            ticker = data.get("ticker") or data.get("symbol")
            exchange = data.get("exchange")
            
            if ticker:
                # Calcul pour différents timeframes
                for timeframe in ["1m", "5m", "15m", "1h"]:
                    indicators = await self.calculate_technical_indicators(
                        ticker, timeframe, exchange
                    )
                    
                    if indicators:
                        await self.save_technical_indicators(indicators)
                        
                        # Publication des indicateurs calculés
                        await self.message_queue.publish(
                            exchange="trading_signals",
                            routing_key="indicators.calculated",
                            message={
                                "type": "technical_indicators",
                                "ticker": ticker,
                                "timeframe": timeframe,
                                "indicators": indicators,
                                "timestamp": datetime.now().isoformat()
                            }
                        )
                        
        except Exception as e:
            logger.error(f"Erreur traitement message: {e}")
    
    async def batch_calculate_indicators(self):
        """Calcul en batch des indicateurs pour tous les tickers."""
        async with get_tsdb_session() as session:
            try:
                # Récupération des tickers actifs
                # TODO: Implémenter la requête pour obtenir les tickers
                
                # Pour l'instant, liste statique
                tickers = [
                    ("AAPL", None),
                    ("BTC/USDT", "binance"),
                    ("ETH/USDT", "binance"),
                    # ... autres tickers
                ]
                
                for ticker, exchange in tickers:
                    for timeframe in self.timeframes:
                        try:
                            indicators = await self.calculate_technical_indicators(
                                ticker, timeframe, exchange
                            )
                            
                            if indicators:
                                await self.save_technical_indicators(indicators)
                                
                        except Exception as e:
                            logger.error(
                                f"Erreur batch calc {ticker} {timeframe}: {e}"
                            )
                            
                        await asyncio.sleep(0.1)  # Rate limiting
                        
            except Exception as e:
                logger.error(f"Erreur batch calculation: {e}")
    
    async def start_processing(self):
        """Démarre le pipeline de traitement."""
        self.is_running = True
        logger.info("Démarrage du pipeline de traitement")
        
        # Démarrage du consumer pour les messages temps réel
        await self.message_queue.consume(
            queue_name="data_processing",
            callback=self.process_market_data_message,
            exchange="market_data",
            routing_key="*.*"
        )
        
        # Boucle de traitement batch
        while self.is_running:
            try:
                start_time = asyncio.get_event_loop().time()
                
                await self.batch_calculate_indicators()
                
                # Maintien de l'intervalle
                elapsed = asyncio.get_event_loop().time() - start_time
                sleep_time = max(0, self.processing_interval - elapsed)
                
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
            except Exception as e:
                logger.error(f"Erreur boucle processing: {e}")
                await asyncio.sleep(60)
    
    async def stop(self):
        """Arrête le pipeline."""
        self.is_running = False
        logger.info("Arrêt du pipeline de traitement")
