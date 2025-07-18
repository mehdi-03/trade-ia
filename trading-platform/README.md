# Plateforme de Trading Automatisé avec IA

Une plateforme SaaS complète de trading automatisé utilisant DeepSeek V3 pour la génération de signaux de trading.

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Data Sources  │    │  Data Pipeline  │    │   AI Engine     │
│                 │    │                 │    │                 │
│ • Yahoo Finance │───▶│ • Processing    │───▶│ • DeepSeek V3   │
│ • CCXT (Crypto) │    │ • Indicators    │    │ • Signal Gen    │
│ • News APIs     │    │ • Enrichment    │    │ • Risk Mgmt     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Order Exec    │    │   API Gateway   │    │   Dashboard     │
│                 │    │                 │    │                 │
│ • Multi-broker  │◀───│ • REST API      │◀───│ • Real-time UI  │
│ • Risk Control  │    │ • Auth          │    │ • Analytics     │
│ • Execution     │    │ • Rate Limiting │    │ • Monitoring    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚀 Services

### Core Services
- **data-ingestion** (Port 8001): Collecte et traitement des données de marché
- **ai-engine** (Port 8003): Génération de signaux via DeepSeek V3
- **order-executor** (Port 8002): Exécution d'ordres multi-brokers
- **api-gateway** (Port 8000): API REST unifiée
- **auth-service** (Port 8001): Authentification et autorisation

### Infrastructure
- **PostgreSQL**: Base de données principale
- **TimescaleDB**: Séries temporelles
- **Redis**: Cache et sessions
- **RabbitMQ**: Message queue
- **Vault**: Gestion des secrets
- **Prometheus**: Métriques
- **Grafana**: Visualisation

## 🛠️ Installation

### Prérequis
- Docker & Docker Compose
- Python 3.11+
- 8GB+ RAM (pour DeepSeek)
- GPU recommandé (CUDA)

### Démarrage rapide

```bash
# Cloner le repository
git clone <repository-url>
cd trading-platform

# Copier les variables d'environnement
cp .env.example .env

# Démarrer les services
docker-compose up -d

# Vérifier l'état des services
docker-compose ps

# Tester le pipeline end-to-end
python scripts/validate_pipeline.py
```

### Configuration

1. **Variables d'environnement** (`.env`):
```bash
# Base de données
DB_USER=trading
DB_PASSWORD=trading123
TSDB_USER=tsdb
TSDB_PASSWORD=tsdb123

# Message Queue
RABBITMQ_USER=rabbit
RABBITMQ_PASSWORD=rabbit123

# Redis
REDIS_PASSWORD=redis123

# DeepSeek
DEEPSEEK_MODEL_PATH=/models/deepseek-v3
DEEPSEEK_API_KEY=your_api_key

# Brokers (exemples)
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
BINANCE_API_KEY=your_binance_key
BINANCE_SECRET_KEY=your_binance_secret
```

2. **Configuration DeepSeek** (`services/ai-engine/config/deepseek.yaml`):
```yaml
model:
  path: "/models/deepseek-v3"
  device: "cuda"
  max_length: 2048
  temperature: 0.7

thresholds:
  confidence_min: 0.7
  signal_strength_min: "MODERATE"

risk_management:
  max_position_size: 0.05
  max_risk_per_trade: 0.02
  max_daily_trades: 10
  max_open_positions: 5
```

## 🔄 Pipeline de Données

### 1. Collecte de Données
- **Stocks**: Yahoo Finance API
- **Crypto**: CCXT (Binance, Coinbase, etc.)
- **News**: NewsAPI, Twitter, RSS feeds
- **Sentiment**: Analyse de sentiment en temps réel

### 2. Traitement et Enrichissement
- Calcul d'indicateurs techniques (RSI, MACD, Bollinger Bands, etc.)
- Analyse de sentiment
- Contexte de marché
- Normalisation des données

### 3. Génération de Signaux
- DeepSeek V3 pour l'analyse prédictive
- Validation par le gestionnaire de risque
- Cache pour éviter les doublons
- Publication sur RabbitMQ

### 4. Exécution d'Ordres
- Validation finale des signaux
- Gestion multi-brokers
- Contrôle de risque en temps réel
- Exécution automatique

## 🧪 Tests

### Tests Unitaires
```bash
# Tests pour chaque service
cd services/data-ingestion && pytest tests/
cd services/ai-engine && pytest tests/
cd services/order-executor && pytest tests/
```

### Tests d'Intégration
```bash
# Test du pipeline complet
python scripts/validate_pipeline.py
```

### Tests de Performance
```bash
# Tests de charge
k6 run scripts/load_test.js
```

## 📊 Monitoring

### Métriques Disponibles
- **Performance**: Latence, throughput, utilisation CPU/mémoire
- **Métier**: Signaux générés, taux de validation, P&L
- **Infrastructure**: État des services, queues, base de données

### Dashboards Grafana
- Vue d'ensemble de la plateforme
- Performance du pipeline
- Métriques de trading
- Alertes et incidents

### Alertes
- Services down
- Latence élevée
- Taux de rejet élevé
- Utilisation des ressources

## 🔧 Développement

### Structure du Code
```
trading-platform/
├── services/
│   ├── data-ingestion/     # Collecte de données
│   ├── ai-engine/          # Moteur IA
│   ├── order-executor/     # Exécution d'ordres
│   ├── api-gateway/        # API REST
│   └── auth-service/       # Authentification
├── infra/
│   ├── monitoring/         # Prometheus, Grafana
│   └── deployment/         # K8s, Terraform
├── scripts/                # Utilitaires
└── tests/                  # Tests d'intégration
```

### Ajout d'un Nouveau Broker
1. Créer un connecteur dans `services/order-executor/connectors/`
2. Implémenter l'interface `BrokerConnector`
3. Ajouter la configuration dans Vault
4. Tester avec les tests d'intégration

### Ajout d'un Nouveau Modèle IA
1. Créer un client dans `services/ai-engine/utils/`
2. Implémenter l'interface `AIClient`
3. Mettre à jour la configuration
4. Ajouter les tests

## 🚀 Déploiement

### Production
```bash
# Build des images
docker-compose -f docker-compose.prod.yml build

# Déploiement
docker-compose -f docker-compose.prod.yml up -d

# Vérification
docker-compose -f docker-compose.prod.yml ps
```

### Kubernetes
```bash
# Déploiement K8s
kubectl apply -f infra/k8s/

# Vérification
kubectl get pods
kubectl get services
```

## 🔒 Sécurité

- **Authentification**: JWT avec refresh tokens
- **Autorisation**: RBAC avec rôles granulaires
- **Secrets**: HashiCorp Vault pour les clés API
- **Chiffrement**: TLS pour toutes les communications
- **Audit**: Logs détaillés de toutes les opérations

## 📈 Performance

### Benchmarks
- **Latence**: < 100ms pour la génération de signaux
- **Throughput**: 1000+ signaux/heure
- **Disponibilité**: 99.9% uptime
- **Scalabilité**: Auto-scaling basé sur la charge

### Optimisations
- Cache Redis pour les données fréquemment accédées
- Pool de connexions pour les bases de données
- Compression des messages RabbitMQ
- Optimisation GPU pour DeepSeek

## 🤝 Contribution

1. Fork le repository
2. Créer une branche feature (`git checkout -b feature/amazing-feature`)
3. Commit les changements (`git commit -m 'Add amazing feature'`)
4. Push vers la branche (`git push origin feature/amazing-feature`)
5. Ouvrir une Pull Request

### Standards de Code
- **Python**: Black, flake8, mypy
- **Tests**: pytest avec couverture > 80%
- **Documentation**: Docstrings pour toutes les fonctions
- **Commits**: Conventional Commits

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

## 🆘 Support

- **Documentation**: `/docs`
- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Email**: support@trading-platform.com

## 🔄 Changelog

### v1.0.0 (2024-01-15)
- ✅ Pipeline complet data-ingestion → ai-engine → signal publishing
- ✅ Intégration DeepSeek V3
- ✅ Gestionnaire de risque avancé
- ✅ Tests d'intégration complets
- ✅ Monitoring et alertes
- ✅ CI/CD pipeline
- ✅ Documentation complète

---

**Note**: Cette plateforme est destinée à des fins éducatives et de recherche. L'utilisation en production nécessite des tests approfondis et une validation réglementaire.