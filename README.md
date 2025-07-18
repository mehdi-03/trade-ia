# 🤖 TradeIA - Plateforme de Trading Automatisé SaaS

Une plateforme complète de trading automatisé basée sur l'intelligence artificielle, intégrant DeepSeek-V3 pour la génération de signaux et supportant plus de 150 exchanges crypto et brokers traditionnels.

## 📋 Table des Matières

- [Architecture Générale](#architecture-générale)
- [Fonctionnalités](#fonctionnalités)
- [Technologies](#technologies)
- [Installation](#installation)
- [Configuration](#configuration)
- [API Documentation](#api-documentation)
- [Déploiement](#déploiement)
- [Contribuer](#contribuer)
- [Licence](#licence)

## 🏗️ Architecture Générale

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   API Gateway   │    │   Dashboard     │
│   (React/Vue)   │◄──►│   (FastAPI)     │◄──►│   (Back-office) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Data Layer    │    │   AI Engine     │    │   Execution     │
│   (TimescaleDB) │◄──►│   (DeepSeek-V3) │◄──►│   (Brokers)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Monitoring    │    │   Security      │    │   Queue System  │
│   (Prometheus)  │    │   (Vault)       │    │   (RabbitMQ)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## ✨ Fonctionnalités

### 🔄 Ingestion et Préparation des Données
- **Sources de données temps réel** :
  - Yahoo Finance (`yfinance`) pour actions et indices
  - CCXT pour +150 exchanges crypto
  - NewsAPI et Twitter API pour sentiment
- **Stockage** : TimescaleDB/InfluxDB pour séries temporelles
- **Orchestration** : Prefect/Airflow pour pipelines ETL
- **Backtesting** : Backtrader et finrl-deepseek

### 🧠 Intelligence Artificielle (DeepSeek-V3)
- **Modèle** : Intégration de `deepseek-ai/DeepSeek-V3` (Apache 2.0)
- **Signaux** : Génération automatique de signaux de trading
- **Risk Management** : Stop-loss, sizing, drawdown maximum
- **Optimisation** : Hyperparamètres via Optuna

### 💼 Moteur d'Exécution Multi-Broker
- **Connecteurs** :
  - CCXT (crypto)
  - QuickFIX (institutionnel)
  - Alpaca, IB_insync, python-binance, oandapyV20
- **Order Manager** : Gestion centralisée des ordres
- **Queue System** : RabbitMQ/Kafka pour l'asynchrone

### 🔐 Sécurité et Credentials
- **Vault** : HashiCorp Vault / AWS Secrets Manager
- **Chiffrement** : Données au repos et en transit
- **Rotation** : Clés API automatique

### 🖥️ Interface Utilisateur
- **Dashboard Public** : React/Vue.js
- **Back-office** : Supervision des bots
- **API** : REST/WebSocket (FastAPI)
- **Paiements** : Stripe/Paddle
- **Chat DeepSeek** : page web minimaliste disponible via l'API Gateway

### 📊 Monitoring et Alerting
- **Métriques** : Prometheus + Grafana
- **Logs** : ELK Stack
- **Alerting** : Slack, Email, SMS, PagerDuty
- **Rapports** : PDF/Excel automatiques

## 🛠️ Technologies

### Backend
- **Python 3.11+**
- **FastAPI** - API REST/WebSocket
- **DeepSeek-V3** - Modèle d'IA
- **CCXT** - Connecteurs crypto
- **QuickFIX** - Connecteurs FIX
- **TimescaleDB/InfluxDB** - Base de données temporelle
- **RabbitMQ/Kafka** - Message queue
- **Prefect/Airflow** - Orchestration

### Frontend
- **React/Vue.js** - Interface utilisateur
- **TypeScript** - Typage statique
- **Tailwind CSS** - Styling
- **Chart.js/D3.js** - Visualisations

### Infrastructure
- **Docker** - Containerisation
- **Kubernetes** - Orchestration
- **Prometheus** - Monitoring
- **Grafana** - Dashboards
- **HashiCorp Vault** - Secrets management

## 🚀 Installation

### Prérequis
- Python 3.11+
- Docker & Docker Compose
- Node.js 18+
- PostgreSQL 14+

### Installation Rapide

```bash
# Cloner le repository
git clone https://github.com/votre-org/trade-ia.git
cd trade-ia

# Installation backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Installation frontend
cd ../frontend
npm install

# Démarrage avec Docker Compose
cd ..
docker-compose up -d
```

### Configuration Environnement

```bash
# Copier les fichiers de configuration
cp .env.example .env
cp config/config.example.yaml config/config.yaml

# Éditer les variables d'environnement
nano .env
```

## ⚙️ Configuration

### Variables d'Environnement

```env
# Base de données
DATABASE_URL=postgresql://user:pass@localhost:5432/tradeia
TIMESCALE_URL=postgresql://user:pass@localhost:5433/timeseries

# Brokers
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
BINANCE_API_KEY=your_binance_key
BINANCE_SECRET_KEY=your_binance_secret

# IA
DEEPSEEK_MODEL_PATH=/models/deepseek-v3
OPENAI_API_KEY=your_openai_key

# Sécurité
VAULT_ADDR=http://localhost:8200
VAULT_TOKEN=your_vault_token

# Monitoring
PROMETHEUS_URL=http://localhost:9090
GRAFANA_URL=http://localhost:3000
```

### Configuration des Brokers

```yaml
# config/brokers.yaml
brokers:
  alpaca:
    type: alpaca
    api_key: ${ALPACA_API_KEY}
    secret_key: ${ALPACA_SECRET_KEY}
    paper: true
    
  binance:
    type: ccxt
    exchange: binance
    api_key: ${BINANCE_API_KEY}
    secret: ${BINANCE_SECRET_KEY}
    
  interactive_brokers:
    type: ib_insync
    host: 127.0.0.1
    port: 7497
    client_id: 1
```

## 📚 API Documentation

### Endpoints Principaux

#### Signaux de Trading
```http
GET /api/v1/signals
POST /api/v1/signals/generate
GET /api/v1/signals/{signal_id}
```

#### Ordres
```http
POST /api/v1/orders
GET /api/v1/orders
GET /api/v1/orders/{order_id}
PUT /api/v1/orders/{order_id}
```

#### Positions
```http
GET /api/v1/positions
GET /api/v1/positions/{symbol}
```

#### Performance
```http
GET /api/v1/performance
GET /api/v1/performance/backtest
GET /api/v1/performance/reports
```

### WebSocket Events

```javascript
// Connexion WebSocket
const ws = new WebSocket('ws://localhost:8000/ws');

// Écouter les signaux en temps réel
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'signal') {
    console.log('Nouveau signal:', data.signal);
  }
};
```

## 🚀 Déploiement

### Docker Compose (Développement)

```bash
# Démarrage complet
docker-compose up -d

# Services disponibles
# - API: http://localhost:8000
# - Dashboard: http://localhost:3000
# - Grafana: http://localhost:3001
# - Prometheus: http://localhost:9090
```

### Kubernetes (Production)

```bash
# Déploiement sur cluster K8s
kubectl apply -f k8s/

# Vérification des pods
kubectl get pods -n tradeia

# Logs des services
kubectl logs -f deployment/tradeia-api -n tradeia
```

### CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml
name: Deploy TradeIA

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: |
          cd backend
          python -m pytest
          
  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to production
        run: |
          kubectl apply -f k8s/
```

## 📁 Structure du Projet

```
trade-ia/
├── backend/
│   ├── app/
│   │   ├── api/           # Endpoints FastAPI
│   │   ├── core/          # Configuration et sécurité
│   │   ├── models/        # Modèles de données
│   │   ├── services/      # Logique métier
│   │   └── utils/         # Utilitaires
│   ├── connectors/        # Connecteurs brokers
│   ├── ai/               # Intégration DeepSeek
│   ├── etl/              # Pipelines de données
│   └── tests/            # Tests unitaires
├── frontend/
│   ├── src/
│   │   ├── components/   # Composants React/Vue
│   │   ├── pages/        # Pages de l'application
│   │   ├── services/     # Services API
│   │   └── utils/        # Utilitaires frontend
│   └── public/           # Assets statiques
├── infrastructure/
│   ├── docker/           # Dockerfiles
│   ├── k8s/              # Manifests Kubernetes
│   └── terraform/        # Infrastructure as Code
├── docs/                 # Documentation
└── scripts/              # Scripts utilitaires
```

## 🔧 Développement

### Ajouter un Nouveau Broker

1. **Créer le connecteur** :
```python
# connectors/new_broker.py
from app.core.connector import BrokerConnector

class NewBrokerConnector(BrokerConnector):
    def initialize(self):
        # Configuration du broker
        pass
        
    def place_order(self, order):
        # Placement d'ordre
        pass
        
    def fetch_positions(self):
        # Récupération des positions
        pass
```

2. **Enregistrer le connecteur** :
```python
# app/core/registry.py
BROKER_REGISTRY = {
    'new_broker': NewBrokerConnector
}
```

### Ajouter un Nouveau Signal

1. **Créer le générateur** :
```python
# ai/signals/new_signal.py
from app.core.signal import SignalGenerator

class NewSignalGenerator(SignalGenerator):
    def generate(self, data):
        # Logique de génération
        return signal
```

2. **Configurer dans l'orchestrateur** :
```yaml
# config/signals.yaml
signals:
  new_signal:
    generator: NewSignalGenerator
    interval: 1h
    symbols: ["BTC/USD", "ETH/USD"]
```

## 📊 Monitoring et Alerting

### Métriques Clés

- **Performance** : Sharpe ratio, drawdown, win rate
- **Technique** : Latence API, taux d'erreur, utilisation CPU/RAM
- **Business** : Nombre d'utilisateurs, volume d'ordres, P&L

### Alertes Configurées

```yaml
# config/alerts.yaml
alerts:
  - name: "Drawdown Excessif"
    condition: "drawdown > 10%"
    channels: ["slack", "email"]
    
  - name: "Erreur Broker"
    condition: "broker_error_rate > 5%"
    channels: ["pagerduty"]
    
  - name: "Latence API"
    condition: "api_latency > 1000ms"
    channels: ["slack"]
```

## 🤝 Contribuer

1. Fork le projet
2. Créer une branche feature (`git checkout -b feature/AmazingFeature`)
3. Commit les changements (`git commit -m 'Add AmazingFeature'`)
4. Push vers la branche (`git push origin feature/AmazingFeature`)
5. Ouvrir une Pull Request

### Standards de Code

- **Python** : PEP 8, type hints, docstrings
- **JavaScript** : ESLint, Prettier, JSDoc
- **Tests** : Couverture > 80%
- **Commits** : Conventional Commits

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

## 🆘 Support

- **Documentation** : [docs.tradeia.com](https://docs.tradeia.com)
- **Issues** : [GitHub Issues](https://github.com/votre-org/trade-ia/issues)
- **Discord** : [Serveur Discord](https://discord.gg/tradeia)
- **Email** : support@tradeia.com

---

**⚠️ Avertissement** : Le trading automatisé comporte des risques. Cette plateforme est fournie "en l'état" sans garantie. Utilisez à vos propres risques et responsabilités. 
