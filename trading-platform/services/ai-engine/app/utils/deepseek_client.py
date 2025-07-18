"""
Client pour interagir avec DeepSeek-V3 via gRPC.
"""

import os
import grpc
import asyncio
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
import yaml
try:
    import torch
except ImportError:  # pragma: no cover - optional dependency
    class _DummyTorch:
        class cuda:
            @staticmethod
            def is_available() -> bool:
                return False

    torch = _DummyTorch()
from datetime import datetime
import pandas as pd

# Import des protobuf générés (à créer)
# from app.proto import deepseek_pb2, deepseek_pb2_grpc

logger = structlog.get_logger()


class DeepSeekClient:
    """Client pour communiquer avec le modèle DeepSeek-V3."""
    
    def __init__(self, config_path: str = "config/deepseek.yaml"):
        """Initialise le client DeepSeek.
        
        Args:
            config_path: Chemin vers le fichier de configuration
        """
        self.config = self._load_config(config_path)
        self.channel = None
        self.stub = None
        self.model_loaded = False
        
        # Configuration du modèle
        self.model_path = self.config.get("model_path", "/models/deepseek-v3")
        self.device = self.config.get("device", "cuda" if torch.cuda.is_available() else "cpu")
        self.batch_size = self.config.get("batch_size", 32)
        self.max_sequence_length = self.config.get("max_sequence_length", 2048)
        
        # Seuils pour la génération de signaux
        self.thresholds = self.config.get("thresholds", {})
        self.confidence_threshold = self.thresholds.get("confidence", 0.7)
        self.signal_thresholds = {
            "strong_buy": self.thresholds.get("strong_buy", 0.85),
            "buy": self.thresholds.get("buy", 0.65),
            "sell": self.thresholds.get("sell", -0.65),
            "strong_sell": self.thresholds.get("strong_sell", -0.85),
        }
        
    def _load_config(self, config_path: str) -> Dict:
        """Charge la configuration depuis un fichier YAML."""
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    return yaml.safe_load(f)
            else:
                logger.warning(f"Config file not found: {config_path}, using defaults")
                return self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """Retourne la configuration par défaut."""
        return {
            "model_path": "/models/deepseek-v3",
            "device": "cuda",
            "batch_size": 32,
            "max_sequence_length": 2048,
            "grpc_server": "localhost:50051",
            "thresholds": {
                "confidence": 0.7,
                "strong_buy": 0.85,
                "buy": 0.65,
                "sell": -0.65,
                "strong_sell": -0.85,
            },
            "features": {
                "technical_indicators": [
                    "rsi", "macd", "bollinger_bands", "sma", "ema",
                    "atr", "adx", "stochastic", "obv"
                ],
                "timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"],
                "lookback_periods": {
                    "1m": 1440,  # 24 heures
                    "5m": 288,   # 24 heures
                    "15m": 96,   # 24 heures
                    "1h": 168,   # 7 jours
                    "4h": 168,   # 28 jours
                    "1d": 365,   # 1 an
                }
            }
        }
    
    async def connect(self):
        """Établit la connexion gRPC avec le serveur DeepSeek."""
        try:
            # Pour l'instant, utilisation directe du modèle local
            # TODO: Implémenter le serveur gRPC séparé
            
            # Simulation de connexion
            self.model_loaded = True
            logger.info("DeepSeek client connected (local mode)")
            
            # Chargement du modèle
            await self._load_model()
            
        except Exception as e:
            logger.error(f"Failed to connect to DeepSeek: {e}")
            raise
    
    async def _load_model(self):
        """Charge le modèle DeepSeek localement."""
        try:
            # TODO: Implémenter le chargement réel du modèle DeepSeek-V3
            # Pour l'instant, simulation
            logger.info(f"Loading DeepSeek model from {self.model_path}")
            await asyncio.sleep(2)  # Simulation du temps de chargement
            logger.info("DeepSeek model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def normalize_timeseries(self, data: pd.DataFrame) -> np.ndarray:
        """Normalise les séries temporelles pour l'entrée du modèle.
        
        Args:
            data: DataFrame avec colonnes OHLCV et indicateurs techniques
            
        Returns:
            Array numpy normalisé
        """
        try:
            # Colonnes requises
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            
            # Vérification des colonnes
            for col in required_cols:
                if col not in data.columns:
                    raise ValueError(f"Missing required column: {col}")
            
            # Normalisation des prix (pourcentage de changement)
            price_cols = ['open', 'high', 'low', 'close']
            for col in price_cols:
                data[f'{col}_pct'] = data[col].pct_change()
            
            # Normalisation du volume (z-score)
            data['volume_zscore'] = (data['volume'] - data['volume'].mean()) / data['volume'].std()
            
            # Ajout d'indicateurs techniques si pas présents
            if 'rsi' not in data.columns:
                # Calcul simplifié du RSI
                delta = data['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                data['rsi'] = 100 - (100 / (1 + rs))
            
            # Sélection des features finales
            feature_cols = [
                'open_pct', 'high_pct', 'low_pct', 'close_pct', 'volume_zscore',
                'rsi'
            ]
            
            # Ajout d'autres indicateurs s'ils existent
            for col in ['macd', 'sma_50', 'sma_200', 'atr', 'adx']:
                if col in data.columns:
                    feature_cols.append(col)
            
            # Création de l'array numpy
            features = data[feature_cols].fillna(0).values
            
            # Normalisation finale entre -1 et 1
            features = np.clip(features, -3, 3) / 3
            
            return features
            
        except Exception as e:
            logger.error(f"Error normalizing timeseries: {e}")
            raise
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def predict_signals(
        self, 
        timeseries_data: Dict[str, pd.DataFrame],
        market_context: Optional[Dict] = None
    ) -> List[Dict]:
        """Génère des signaux de trading à partir des données.
        
        Args:
            timeseries_data: Dict avec clé=timeframe, valeur=DataFrame
            market_context: Contexte de marché optionnel
            
        Returns:
            Liste de signaux générés
        """
        try:
            if not self.model_loaded:
                await self.connect()
            
            signals = []
            
            # Traitement par timeframe
            for timeframe, data in timeseries_data.items():
                if data is None or len(data) < 50:
                    continue
                
                # Normalisation des données
                normalized_data = self.normalize_timeseries(data)
                
                # Prédiction (simulation pour l'instant)
                prediction = await self._run_prediction(
                    normalized_data, 
                    timeframe,
                    market_context
                )
                
                # Conversion en signal si confiance suffisante
                if prediction['confidence'] >= self.confidence_threshold:
                    signal = self._create_signal(prediction, data, timeframe)
                    if signal:
                        signals.append(signal)
            
            # Agrégation et filtrage des signaux
            final_signals = self._aggregate_signals(signals)
            
            return final_signals
            
        except Exception as e:
            logger.error(f"Error predicting signals: {e}")
            return []
    
    async def _run_prediction(
        self, 
        features: np.ndarray,
        timeframe: str,
        market_context: Optional[Dict] = None
    ) -> Dict:
        """Exécute la prédiction sur le modèle.
        
        Pour l'instant, simulation avec logique basique.
        TODO: Intégrer le vrai modèle DeepSeek.
        """
        try:
            # Simulation de prédiction
            # En production, appel au modèle DeepSeek réel
            
            # Analyse des features
            latest_features = features[-1]
            recent_trend = np.mean(features[-20:, 3])  # close_pct moyen
            
            # RSI
            rsi = features[-1, 5] * 100 if len(features[0]) > 5 else 50
            
            # Logique de décision simplifiée
            score = 0.0
            
            # Tendance
            if recent_trend > 0.001:
                score += 0.3
            elif recent_trend < -0.001:
                score -= 0.3
            
            # RSI
            if rsi < 30:
                score += 0.4
            elif rsi > 70:
                score -= 0.4
            
            # Contexte de marché
            if market_context:
                if market_context.get('vix_level', 20) > 30:
                    score *= 0.7  # Réduction en cas de forte volatilité
            
            # Normalisation du score entre -1 et 1
            score = np.tanh(score)
            
            # Calcul de la confiance
            confidence = abs(score)
            
            # Type de signal
            if score > self.signal_thresholds['strong_buy']:
                signal_type = "STRONG_BUY"
            elif score > self.signal_thresholds['buy']:
                signal_type = "BUY"
            elif score < self.signal_thresholds['strong_sell']:
                signal_type = "STRONG_SELL"
            elif score < self.signal_thresholds['sell']:
                signal_type = "SELL"
            else:
                signal_type = "HOLD"
            
            return {
                "score": score,
                "confidence": confidence,
                "signal_type": signal_type,
                "timeframe": timeframe,
                "features": {
                    "rsi": rsi,
                    "trend": recent_trend,
                    "volatility": np.std(features[-20:, 3])
                }
            }
            
        except Exception as e:
            logger.error(f"Error in prediction: {e}")
            return {
                "score": 0.0,
                "confidence": 0.0,
                "signal_type": "HOLD",
                "timeframe": timeframe,
                "features": {}
            }
    
    def _create_signal(self, prediction: Dict, data: pd.DataFrame, timeframe: str) -> Optional[Dict]:
        """Crée un signal structuré à partir de la prédiction."""
        try:
            if prediction['signal_type'] == "HOLD":
                return None
            
            latest_price = float(data['close'].iloc[-1])
            
            # Calcul du stop loss et take profit
            atr = data.get('atr', data['close'].rolling(14).std()).iloc[-1]
            
            if prediction['signal_type'] in ["BUY", "STRONG_BUY"]:
                stop_loss = latest_price - (2 * atr)
                take_profit = latest_price + (3 * atr)
            else:
                stop_loss = latest_price + (2 * atr)
                take_profit = latest_price - (3 * atr)
            
            # Risk/Reward ratio
            risk = abs(latest_price - stop_loss)
            reward = abs(take_profit - latest_price)
            risk_reward_ratio = reward / risk if risk > 0 else 0
            
            return {
                "signal_type": prediction['signal_type'],
                "confidence": prediction['confidence'],
                "score": prediction['score'],
                "entry_price": latest_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_reward_ratio": risk_reward_ratio,
                "timeframe": timeframe,
                "timestamp": datetime.now(),
                "technical_indicators": prediction['features'],
                "reasoning": self._generate_reasoning(prediction, data)
            }
            
        except Exception as e:
            logger.error(f"Error creating signal: {e}")
            return None
    
    def _generate_reasoning(self, prediction: Dict, data: pd.DataFrame) -> str:
        """Génère une explication textuelle du signal."""
        features = prediction['features']
        signal = prediction['signal_type']
        
        reasoning_parts = []
        
        # Signal principal
        reasoning_parts.append(f"Signal {signal} généré avec confiance {prediction['confidence']:.2%}")
        
        # RSI
        if 'rsi' in features:
            rsi = features['rsi']
            if rsi < 30:
                reasoning_parts.append(f"RSI survendu à {rsi:.1f}")
            elif rsi > 70:
                reasoning_parts.append(f"RSI suracheté à {rsi:.1f}")
        
        # Tendance
        if 'trend' in features:
            trend = features['trend']
            if trend > 0.001:
                reasoning_parts.append("Tendance haussière confirmée")
            elif trend < -0.001:
                reasoning_parts.append("Tendance baissière détectée")
        
        # Volatilité
        if 'volatility' in features:
            vol = features['volatility']
            if vol > 0.02:
                reasoning_parts.append("Volatilité élevée, prudence recommandée")
        
        return ". ".join(reasoning_parts)
    
    def _aggregate_signals(self, signals: List[Dict]) -> List[Dict]:
        """Agrège et filtre les signaux de différents timeframes."""
        if not signals:
            return []
        
        # Regroupement par type de signal
        buy_signals = [s for s in signals if "BUY" in s['signal_type']]
        sell_signals = [s for s in signals if "SELL" in s['signal_type']]
        
        final_signals = []
        
        # Sélection du meilleur signal d'achat
        if buy_signals:
            best_buy = max(buy_signals, key=lambda x: x['confidence'])
            final_signals.append(best_buy)
        
        # Sélection du meilleur signal de vente
        if sell_signals:
            best_sell = max(sell_signals, key=lambda x: x['confidence'])
            final_signals.append(best_sell)
        
        return final_signals
    
    async def close(self):
        """Ferme la connexion au serveur DeepSeek."""
        try:
            if self.channel:
                await self.channel.close()
            logger.info("DeepSeek client closed")
        except Exception as e:
            logger.error(f"Error closing client: {e}")

    async def chat(self, prompt: str, context: Optional[str] = None) -> str:
        """Génère une réponse textuelle à partir du modèle DeepSeek.

        Cette implémentation est simplifiée et sert de démonstration. Elle
        combine le message utilisateur avec un contexte optionnel (par exemple
        les dernières news) avant de l'envoyer au modèle. La réponse retournée
        est simulée tant que l'intégration gRPC complète n'est pas disponible.

        Args:
            prompt: message de l'utilisateur
            context: informations de contexte supplémentaires

        Returns:
            Réponse générée par le modèle
        """
        try:
            if not self.model_loaded:
                await self.connect()

            full_prompt = prompt
            if context:
                full_prompt = f"{context}\n\nUtilisateur: {prompt}"

            # TODO: intégrer l'appel réel au modèle DeepSeek
            return f"Réponse DeepSeek: {full_prompt[:200]}"

        except Exception as e:
            logger.error(f"Error during chat: {e}")
            return "Erreur lors de la génération de la réponse"
