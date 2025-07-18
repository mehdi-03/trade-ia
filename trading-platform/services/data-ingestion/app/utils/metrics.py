"""
Métriques Prometheus pour le monitoring.
"""

from prometheus_client import Counter, Histogram, Gauge, Summary

# Compteurs de collecte de données
data_collection_counter = Counter(
    'data_collection_total',
    'Nombre total de collectes de données',
    ['source', 'ticker']
)

data_collection_errors = Counter(
    'data_collection_errors_total',
    'Nombre total d\'erreurs de collecte',
    ['source', 'ticker']
)

# Histogrammes de latence
data_fetch_duration = Histogram(
    'data_fetch_duration_seconds',
    'Durée de récupération des données',
    ['source', 'operation']
)

db_operation_duration = Histogram(
    'db_operation_duration_seconds',
    'Durée des opérations de base de données',
    ['operation', 'table']
)

# Gauges pour l'état du système
active_collectors = Gauge(
    'active_collectors',
    'Nombre de collecteurs actifs',
    ['type']
)

queue_size = Gauge(
    'message_queue_size',
    'Taille des queues de messages',
    ['queue_name']
)

# Summary pour les indicateurs calculés
technical_indicator_calculation = Summary(
    'technical_indicator_calculation_seconds',
    'Temps de calcul des indicateurs techniques',
    ['indicator', 'timeframe']
)

# Métriques spécifiques au sentiment
sentiment_score_gauge = Gauge(
    'sentiment_score',
    'Score de sentiment actuel',
    ['target', 'source']
)

news_articles_processed = Counter(
    'news_articles_processed_total',
    'Nombre d\'articles de news traités',
    ['source', 'category']
)

# Métriques de performance
memory_usage = Gauge(
    'process_memory_bytes',
    'Utilisation mémoire du processus'
)

cpu_usage = Gauge(
    'process_cpu_percent',
    'Utilisation CPU du processus'
)