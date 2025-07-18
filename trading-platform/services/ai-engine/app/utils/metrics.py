"""
Métriques Prometheus pour le monitoring du service AI.
"""

from prometheus_client import Counter, Histogram, Gauge, Summary

# Compteurs de génération de signaux
signal_generation_counter = Counter(
    'signal_generation_total',
    'Nombre total de signaux générés',
    ['ticker', 'signal_type', 'strength']
)

signal_validation_counter = Counter(
    'signal_validation_total',
    'Nombre total de validations de signaux',
    ['ticker', 'status']
)

# Histogrammes de latence
ai_processing_duration = Histogram(
    'ai_processing_duration_seconds',
    'Durée de traitement par l\'IA',
    ['operation']
)

model_inference_duration = Histogram(
    'model_inference_duration_seconds',
    'Durée d\'inférence du modèle DeepSeek',
    ['model']
)

signal_validation_duration = Histogram(
    'signal_validation_duration_seconds',
    'Durée de validation des signaux',
    ['component']
)

# Gauges pour l'état du système
ai_engine_status = Gauge(
    'ai_engine_status',
    'Statut du moteur IA',
    ['component']
)

model_loaded_status = Gauge(
    'model_loaded_status',
    'Statut de chargement du modèle',
    ['model']
)

active_tickers = Gauge(
    'active_tickers',
    'Nombre de tickers surveillés'
)

signal_cache_size = Gauge(
    'signal_cache_size',
    'Taille du cache de signaux'
)

# Summary pour les scores de confiance
signal_confidence_score = Summary(
    'signal_confidence_score',
    'Score de confiance des signaux générés',
    ['signal_type']
)

# Métriques spécifiques au risque
risk_validation_failures = Counter(
    'risk_validation_failures_total',
    'Nombre d\'échecs de validation de risque',
    ['risk_type']
)

daily_trades_count = Gauge(
    'daily_trades_count',
    'Nombre de trades effectués aujourd\'hui'
)

open_positions_count = Gauge(
    'open_positions_count',
    'Nombre de positions ouvertes'
)

# Métriques de performance
memory_usage = Gauge(
    'ai_engine_memory_bytes',
    'Utilisation mémoire du service AI'
)

cpu_usage = Gauge(
    'ai_engine_cpu_percent',
    'Utilisation CPU du service AI'
)

# Métriques de qualité des signaux
signal_quality_score = Summary(
    'signal_quality_score',
    'Score de qualité des signaux',
    ['metric']
)

# Métriques de contexte de marché
market_context_metrics = Gauge(
    'market_context_metrics',
    'Métriques de contexte de marché',
    ['metric']
) 