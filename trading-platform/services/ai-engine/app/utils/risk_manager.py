"""
Gestionnaire de risque pour validation des signaux.
"""

from typing import Dict, List, Optional
import structlog
from app.models.signals import RiskParameters, SignalValidation

logger = structlog.get_logger()


class RiskManager:
    """Gestionnaire de risque pour validation des signaux."""
    
    def __init__(self):
        self.max_daily_trades = 10
        self.max_open_positions = 5
        self.max_correlation = 0.7
        self.daily_trades_count = 0
        self.open_positions = []
        
    async def initialize(self):
        """Initialise le gestionnaire de risque."""
        try:
            # TODO: Charger les positions ouvertes depuis la DB
            logger.info("Risk Manager initialisé")
        except Exception as e:
            logger.error(f"Erreur initialisation Risk Manager: {e}")
            raise
    
    async def validate_signal(
        self, 
        signal_data: Dict, 
        risk_params: RiskParameters
    ) -> SignalValidation:
        """Valide un signal selon les règles de risque."""
        validation = SignalValidation(
            signal_id=signal_data.get("id", "unknown"),
            is_valid=True,
            validation_errors=[],
            risk_check_passed=True,
            position_size_check_passed=True,
            correlation_check_passed=True,
            market_hours_check_passed=True,
            liquidity_check_passed=True,
            warnings=[],
            recommendations=[]
        )
        
        try:
            # Vérification de la taille de position
            position_size = signal_data.get("position_size_percent", 0)
            if position_size > risk_params.max_position_size:
                validation.position_size_check_passed = False
                validation.is_valid = False
                validation.validation_errors.append(
                    f"Position size {position_size:.2%} exceeds maximum {risk_params.max_position_size:.2%}"
                )
                validation.adjusted_position_size = risk_params.max_position_size
            
            # Vérification du risque par trade
            entry_price = signal_data.get("entry_price", 0)
            stop_loss = signal_data.get("stop_loss", 0)
            if entry_price and stop_loss:
                risk_amount = abs(entry_price - stop_loss) / entry_price
                if risk_amount > risk_params.max_risk_per_trade:
                    validation.risk_check_passed = False
                    validation.is_valid = False
                    validation.validation_errors.append(
                        f"Risk per trade {risk_amount:.2%} exceeds maximum {risk_params.max_risk_per_trade:.2%}"
                    )
            
            # Vérification du nombre de trades quotidiens
            if self.daily_trades_count >= risk_params.max_daily_trades:
                validation.is_valid = False
                validation.validation_errors.append(
                    f"Daily trade limit reached ({self.daily_trades_count}/{risk_params.max_daily_trades})"
                )
            
            # Vérification du nombre de positions ouvertes
            if len(self.open_positions) >= risk_params.max_open_positions:
                validation.is_valid = False
                validation.validation_errors.append(
                    f"Maximum open positions reached ({len(self.open_positions)}/{risk_params.max_open_positions})"
                )
            
            # Vérification de la corrélation
            if not await self._check_correlation(signal_data):
                validation.correlation_check_passed = False
                validation.is_valid = False
                validation.validation_errors.append(
                    f"Signal would create high correlation with existing positions"
                )
            
            # Vérification des heures de marché
            if not await self._check_market_hours(signal_data):
                validation.market_hours_check_passed = False
                validation.warnings.append("Trading outside normal market hours")
            
            # Vérification de la liquidité
            if not await self._check_liquidity(signal_data):
                validation.liquidity_check_passed = False
                validation.is_valid = False
                validation.validation_errors.append("Insufficient liquidity for this trade")
            
            # Ajustements automatiques
            if validation.is_valid:
                validation = await self._apply_risk_adjustments(validation, signal_data, risk_params)
            
            # Recommandations
            validation.recommendations = self._generate_recommendations(validation, signal_data)
            
        except Exception as e:
            logger.error(f"Erreur validation signal: {e}")
            validation.is_valid = False
            validation.validation_errors.append(f"Validation error: {str(e)}")
        
        return validation
    
    async def _check_correlation(self, signal_data: Dict) -> bool:
        """Vérifie la corrélation avec les positions existantes."""
        try:
            # TODO: Implémenter la vérification de corrélation réelle
            # Pour l'instant, simulation
            return True
        except Exception as e:
            logger.error(f"Erreur vérification corrélation: {e}")
            return False
    
    async def _check_market_hours(self, signal_data: Dict) -> bool:
        """Vérifie si le trading est dans les heures de marché."""
        try:
            # TODO: Implémenter la vérification des heures de marché
            # Pour l'instant, toujours autorisé
            return True
        except Exception as e:
            logger.error(f"Erreur vérification heures marché: {e}")
            return False
    
    async def _check_liquidity(self, signal_data: Dict) -> bool:
        """Vérifie la liquidité disponible."""
        try:
            # TODO: Implémenter la vérification de liquidité
            # Pour l'instant, toujours suffisante
            return True
        except Exception as e:
            logger.error(f"Erreur vérification liquidité: {e}")
            return False
    
    async def _apply_risk_adjustments(
        self, 
        validation: SignalValidation, 
        signal_data: Dict, 
        risk_params: RiskParameters
    ) -> SignalValidation:
        """Applique des ajustements automatiques de risque."""
        try:
            entry_price = signal_data.get("entry_price", 0)
            
            # Ajustement du stop loss si nécessaire
            if not validation.adjusted_stop_loss:
                atr = signal_data.get("technical_indicators", {}).get("atr", 0)
                if atr:
                    if signal_data.get("signal_type") in ["BUY", "STRONG_BUY"]:
                        validation.adjusted_stop_loss = entry_price - (risk_params.stop_loss_atr_multiplier * atr)
                    else:
                        validation.adjusted_stop_loss = entry_price + (risk_params.stop_loss_atr_multiplier * atr)
            
            # Ajustement du take profit si nécessaire
            if not validation.adjusted_take_profit:
                atr = signal_data.get("technical_indicators", {}).get("atr", 0)
                if atr:
                    if signal_data.get("signal_type") in ["BUY", "STRONG_BUY"]:
                        validation.adjusted_take_profit = entry_price + (risk_params.take_profit_atr_multiplier * atr)
                    else:
                        validation.adjusted_take_profit = entry_price - (risk_params.take_profit_atr_multiplier * atr)
            
        except Exception as e:
            logger.error(f"Erreur ajustements risque: {e}")
        
        return validation
    
    def _generate_recommendations(
        self, 
        validation: SignalValidation, 
        signal_data: Dict
    ) -> List[str]:
        """Génère des recommandations basées sur la validation."""
        recommendations = []
        
        # Recommandations basées sur la force du signal
        signal_strength = signal_data.get("signal_strength", "MODERATE")
        if signal_strength == "VERY_STRONG":
            recommendations.append("Signal très fort - considérer une position plus importante")
        elif signal_strength == "WEAK":
            recommendations.append("Signal faible - attendre confirmation ou réduire la taille")
        
        # Recommandations basées sur le risk/reward
        rr_ratio = signal_data.get("risk_reward_ratio", 0)
        if rr_ratio < 1.5:
            recommendations.append("Risk/Reward ratio faible - considérer un take profit plus élevé")
        elif rr_ratio > 3:
            recommendations.append("Risk/Reward ratio excellent - signal de qualité")
        
        # Recommandations basées sur la volatilité
        volatility = signal_data.get("technical_indicators", {}).get("volatility", 0)
        if volatility > 0.05:
            recommendations.append("Volatilité élevée - stop loss plus large recommandé")
        
        return recommendations
    
    async def record_trade(self, signal_data: Dict):
        """Enregistre un trade exécuté."""
        try:
            self.daily_trades_count += 1
            
            # Ajout à la liste des positions ouvertes
            position = {
                "ticker": signal_data.get("ticker"),
                "signal_type": signal_data.get("signal_type"),
                "entry_price": signal_data.get("entry_price"),
                "position_size": signal_data.get("position_size_percent"),
                "timestamp": signal_data.get("timestamp")
            }
            self.open_positions.append(position)
            
            logger.info(f"Trade enregistré: {signal_data.get('ticker')} {signal_data.get('signal_type')}")
            
        except Exception as e:
            logger.error(f"Erreur enregistrement trade: {e}")
    
    async def close_position(self, ticker: str):
        """Ferme une position ouverte."""
        try:
            self.open_positions = [p for p in self.open_positions if p["ticker"] != ticker]
            logger.info(f"Position fermée: {ticker}")
        except Exception as e:
            logger.error(f"Erreur fermeture position: {e}")
    
    def reset_daily_counters(self):
        """Remet à zéro les compteurs quotidiens."""
        self.daily_trades_count = 0
        logger.info("Compteurs quotidiens remis à zéro") 
