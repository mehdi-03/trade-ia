"""
Collecteur de données de marché via Yahoo Finance.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import yfinance as yf
import pandas as pd
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
import os

from app.utils.database import get_db_session
from app.models.market_data import MarketData, Ticker
from app.utils.metrics import data_collection_counter, data_collection_errors

logger = structlog.get_logger()


class MarketDataCollector:
    """Collecteur de données de marché depuis Yahoo Finance."""
    
    def __init__(self):
        self.is_running = False
        self.collection_interval = int(os.getenv("MARKET_DATA_INTERVAL", "60"))  # secondes
        self.tickers: List[str] = self._load_tickers()
        
    def _load_tickers(self) -> List[str]:
        """Charge la liste des tickers à surveiller."""
        # TODO: Charger depuis la base de données
        default_tickers = [
            # Indices
            "^GSPC", "^DJI", "^IXIC", "^VIX",
            # Actions tech
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA",
            # Actions finance
            "JPM", "BAC", "GS", "MS", "WFC",
            # ETFs
            "SPY", "QQQ", "IWM", "DIA", "VTI",
            # Commodités
            "GLD", "SLV", "USO", "UNG",
            # Forex pairs (via ETFs)
            "FXE", "FXY", "FXB", "UUP"
        ]
        return default_tickers
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def fetch_ticker_data(self, ticker: str) -> Optional[Dict]:
        """Récupère les données d'un ticker spécifique."""
        try:
            # Exécution dans un thread pour éviter de bloquer l'event loop
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, self._fetch_ticker_sync, ticker)
            
            if data:
                data_collection_counter.labels(source="yahoo_finance", ticker=ticker).inc()
                logger.info(f"Données récupérées pour {ticker}", ticker=ticker)
            
            return data
            
        except Exception as e:
            data_collection_errors.labels(source="yahoo_finance", ticker=ticker).inc()
            logger.error(f"Erreur lors de la récupération de {ticker}: {e}", ticker=ticker, error=str(e))
            return None
    
    def _fetch_ticker_sync(self, ticker: str) -> Optional[Dict]:
        """Récupération synchrone des données d'un ticker."""
        try:
            stock = yf.Ticker(ticker)
            
            # Récupération des données temps réel
            info = stock.info
            history = stock.history(period="1d", interval="1m")
            
            if history.empty:
                return None
            
            latest = history.iloc[-1]
            
            return {
                "ticker": ticker,
                "timestamp": datetime.now(),
                "open": float(latest.get("Open", 0)),
                "high": float(latest.get("High", 0)),
                "low": float(latest.get("Low", 0)),
                "close": float(latest.get("Close", 0)),
                "volume": int(latest.get("Volume", 0)),
                "bid": float(info.get("bid", 0)),
                "ask": float(info.get("ask", 0)),
                "bid_size": int(info.get("bidSize", 0)),
                "ask_size": int(info.get("askSize", 0)),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "dividend_yield": info.get("dividendYield"),
                "beta": info.get("beta"),
                "52_week_high": info.get("fiftyTwoWeekHigh"),
                "52_week_low": info.get("fiftyTwoWeekLow"),
                "moving_avg_50": info.get("fiftyDayAverage"),
                "moving_avg_200": info.get("twoHundredDayAverage"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
            }
            
        except Exception as e:
            logger.error(f"Erreur sync pour {ticker}: {e}")
            return None
    
    async def save_market_data(self, data: Dict):
        """Sauvegarde les données de marché dans la base de données."""
        async with get_db_session() as session:
            try:
                market_data = MarketData(
                    ticker=data["ticker"],
                    timestamp=data["timestamp"],
                    open_price=data["open"],
                    high_price=data["high"],
                    low_price=data["low"],
                    close_price=data["close"],
                    volume=data["volume"],
                    bid=data.get("bid"),
                    ask=data.get("ask"),
                    bid_size=data.get("bid_size"),
                    ask_size=data.get("ask_size"),
                    metadata={
                        "market_cap": data.get("market_cap"),
                        "pe_ratio": data.get("pe_ratio"),
                        "dividend_yield": data.get("dividend_yield"),
                        "beta": data.get("beta"),
                        "52_week_high": data.get("52_week_high"),
                        "52_week_low": data.get("52_week_low"),
                        "moving_avg_50": data.get("moving_avg_50"),
                        "moving_avg_200": data.get("moving_avg_200"),
                        "sector": data.get("sector"),
                        "industry": data.get("industry"),
                    }
                )
                
                session.add(market_data)
                await session.commit()
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Erreur sauvegarde données: {e}", error=str(e))
    
    async def collect_all_tickers(self):
        """Collecte les données pour tous les tickers."""
        tasks = []
        
        for ticker in self.tickers:
            task = asyncio.create_task(self.fetch_ticker_data(ticker))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Sauvegarde des données valides
        save_tasks = []
        for result in results:
            if isinstance(result, dict) and result:
                save_task = asyncio.create_task(self.save_market_data(result))
                save_tasks.append(save_task)
        
        if save_tasks:
            await asyncio.gather(*save_tasks, return_exceptions=True)
    
    async def start_collection(self):
        """Démarre la collecte périodique des données."""
        self.is_running = True
        logger.info("Démarrage du collecteur de données de marché")
        
        while self.is_running:
            try:
                start_time = asyncio.get_event_loop().time()
                
                await self.collect_all_tickers()
                
                # Calcul du temps d'attente pour maintenir l'intervalle
                elapsed = asyncio.get_event_loop().time() - start_time
                sleep_time = max(0, self.collection_interval - elapsed)
                
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
            except Exception as e:
                logger.error(f"Erreur dans la boucle de collecte: {e}", error=str(e))
                await asyncio.sleep(60)  # Attente avant retry
    
    async def stop(self):
        """Arrête la collecte."""
        self.is_running = False
        logger.info("Arrêt du collecteur de données de marché")