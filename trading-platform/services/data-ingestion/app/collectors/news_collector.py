"""
Collecteur de news et analyse de sentiment.
Sources: NewsAPI, Twitter, Reddit, RSS feeds financiers.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import httpx
from newsapi import NewsApiClient
import tweepy
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
import os
from textblob import TextBlob
import feedparser

from app.utils.database import get_db_session
from app.models.market_data import NewsArticle, SentimentData
from app.utils.metrics import data_collection_counter, data_collection_errors

logger = structlog.get_logger()


class NewsCollector:
    """Collecteur de news et analyse de sentiment."""
    
    def __init__(self):
        self.is_running = False
        self.collection_interval = int(os.getenv("NEWS_COLLECTION_INTERVAL", "300"))  # 5 minutes
        
        # APIs
        self.newsapi = self._init_newsapi()
        self.twitter = self._init_twitter()
        
        # Sources RSS
        self.rss_feeds = {
            "reuters_markets": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
            "bloomberg": "https://feeds.bloomberg.com/markets/news.rss",
            "wsj_markets": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
            "ft_markets": "https://www.ft.com/markets?format=rss",
            "cnbc_markets": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069",
            "marketwatch": "http://feeds.marketwatch.com/marketwatch/topstories",
        }
        
        # Mots-clés à surveiller
        self.keywords = self._load_keywords()
        
    def _init_newsapi(self) -> Optional[NewsApiClient]:
        """Initialise NewsAPI."""
        api_key = os.getenv("NEWSAPI_KEY")
        if api_key:
            return NewsApiClient(api_key=api_key)
        logger.warning("NewsAPI key non configurée")
        return None
    
    def _init_twitter(self) -> Optional[tweepy.Client]:
        """Initialise Twitter API v2."""
        bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
        if bearer_token:
            return tweepy.Client(bearer_token=bearer_token)
        logger.warning("Twitter bearer token non configuré")
        return None
    
    def _load_keywords(self) -> Dict[str, List[str]]:
        """Charge les mots-clés à surveiller par catégorie."""
        return {
            "crypto": [
                "bitcoin", "ethereum", "cryptocurrency", "blockchain",
                "defi", "nft", "web3", "crypto regulation", "SEC crypto",
                "binance", "coinbase", "crypto hack", "stablecoin"
            ],
            "stocks": [
                "stock market", "S&P 500", "nasdaq", "dow jones",
                "earnings", "IPO", "merger", "acquisition", "fed",
                "interest rates", "inflation", "recession", "bull market",
                "bear market"
            ],
            "forex": [
                "forex", "currency", "dollar", "euro", "yen",
                "pound", "yuan", "exchange rate", "central bank",
                "monetary policy"
            ],
            "commodities": [
                "gold", "silver", "oil", "crude", "natural gas",
                "copper", "wheat", "corn", "commodity prices"
            ],
            "companies": [
                "Apple", "Microsoft", "Google", "Amazon", "Tesla",
                "Meta", "Nvidia", "JPMorgan", "Goldman Sachs",
                "Berkshire Hathaway"
            ]
        }
    
    def analyze_sentiment(self, text: str) -> Dict[str, float]:
        """Analyse le sentiment d'un texte."""
        try:
            blob = TextBlob(text)
            
            # Sentiment principal
            polarity = blob.sentiment.polarity  # -1 à 1
            subjectivity = blob.sentiment.subjectivity  # 0 à 1
            
            # Classification
            if polarity > 0.1:
                sentiment_label = "positive"
                confidence = min(polarity, 1.0)
            elif polarity < -0.1:
                sentiment_label = "negative"
                confidence = min(abs(polarity), 1.0)
            else:
                sentiment_label = "neutral"
                confidence = 1.0 - abs(polarity)
            
            return {
                "polarity": polarity,
                "subjectivity": subjectivity,
                "sentiment": sentiment_label,
                "confidence": confidence
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse sentiment: {e}")
            return {
                "polarity": 0.0,
                "subjectivity": 0.5,
                "sentiment": "neutral",
                "confidence": 0.0
            }
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def fetch_newsapi_articles(self) -> List[Dict]:
        """Récupère les articles via NewsAPI."""
        if not self.newsapi:
            return []
            
        articles = []
        try:
            # Recherche par catégories
            for category, keywords in self.keywords.items():
                query = " OR ".join(keywords[:5])  # Limite à 5 mots-clés par requête
                
                response = self.newsapi.get_everything(
                    q=query,
                    language="en",
                    sort_by="publishedAt",
                    from_param=(datetime.now() - timedelta(hours=24)).isoformat(),
                    page_size=20
                )
                
                for article in response.get("articles", []):
                    sentiment = self.analyze_sentiment(
                        f"{article.get('title', '')} {article.get('description', '')}"
                    )
                    
                    articles.append({
                        "source": "newsapi",
                        "category": category,
                        "title": article.get("title"),
                        "description": article.get("description"),
                        "url": article.get("url"),
                        "published_at": datetime.fromisoformat(
                            article.get("publishedAt").replace("Z", "+00:00")
                        ),
                        "author": article.get("author"),
                        "source_name": article.get("source", {}).get("name"),
                        "sentiment": sentiment,
                        "content": article.get("content")
                    })
                    
                await asyncio.sleep(0.1)  # Rate limiting
                
            data_collection_counter.labels(source="newsapi", ticker="news").inc()
            return articles
            
        except Exception as e:
            data_collection_errors.labels(source="newsapi", ticker="news").inc()
            logger.error(f"Erreur NewsAPI: {e}")
            return []
    
    async def fetch_twitter_sentiment(self) -> List[Dict]:
        """Récupère et analyse les tweets pertinents."""
        if not self.twitter:
            return []
            
        tweets_data = []
        try:
            # Top influenceurs crypto/finance à suivre
            influencers = [
                "elonmusk", "CathieDWood", "jimcramer", "WarrenBuffett",
                "michael_saylor", "APompliano", "VitalikButerin"
            ]
            
            for category, keywords in list(self.keywords.items())[:3]:  # Limite aux 3 premières catégories
                query = f"({' OR '.join(keywords[:3])}) -is:retweet lang:en"
                
                tweets = self.twitter.search_recent_tweets(
                    query=query,
                    max_results=50,
                    tweet_fields=["created_at", "author_id", "public_metrics"]
                )
                
                if tweets.data:
                    for tweet in tweets.data:
                        sentiment = self.analyze_sentiment(tweet.text)
                        
                        tweets_data.append({
                            "source": "twitter",
                            "category": category,
                            "text": tweet.text,
                            "created_at": tweet.created_at,
                            "author_id": tweet.author_id,
                            "metrics": tweet.public_metrics,
                            "sentiment": sentiment
                        })
                
                await asyncio.sleep(1)  # Rate limiting
                
            data_collection_counter.labels(source="twitter", ticker="sentiment").inc()
            return tweets_data
            
        except Exception as e:
            data_collection_errors.labels(source="twitter", ticker="sentiment").inc()
            logger.error(f"Erreur Twitter: {e}")
            return []
    
    async def fetch_rss_feeds(self) -> List[Dict]:
        """Récupère les articles des flux RSS."""
        articles = []
        
        async with httpx.AsyncClient() as client:
            for feed_name, feed_url in self.rss_feeds.items():
                try:
                    response = await client.get(feed_url, timeout=10.0)
                    feed = feedparser.parse(response.text)
                    
                    for entry in feed.entries[:10]:  # Limite à 10 articles par feed
                        # Analyse du sentiment
                        text = f"{entry.get('title', '')} {entry.get('summary', '')}"
                        sentiment = self.analyze_sentiment(text)
                        
                        # Catégorisation basique
                        category = "general"
                        text_lower = text.lower()
                        for cat, keywords in self.keywords.items():
                            if any(kw in text_lower for kw in keywords):
                                category = cat
                                break
                        
                        articles.append({
                            "source": f"rss_{feed_name}",
                            "category": category,
                            "title": entry.get("title"),
                            "description": entry.get("summary"),
                            "url": entry.get("link"),
                            "published_at": datetime.now(),  # Parser la date si disponible
                            "sentiment": sentiment
                        })
                        
                except Exception as e:
                    logger.error(f"Erreur RSS {feed_name}: {e}")
                    
        return articles
    
    async def save_news_data(self, articles: List[Dict]):
        """Sauvegarde les articles en base de données."""
        async with get_db_session() as session:
            try:
                for article in articles:
                    news = NewsArticle(
                        source=article["source"],
                        category=article["category"],
                        title=article["title"],
                        description=article.get("description"),
                        url=article.get("url"),
                        published_at=article["published_at"],
                        author=article.get("author"),
                        sentiment_score=article["sentiment"]["polarity"],
                        sentiment_label=article["sentiment"]["sentiment"],
                        sentiment_confidence=article["sentiment"]["confidence"],
                        content=article.get("content"),
                        metadata={
                            "source_name": article.get("source_name"),
                            "subjectivity": article["sentiment"]["subjectivity"]
                        }
                    )
                    session.add(news)
                
                await session.commit()
                logger.info(f"Sauvegardé {len(articles)} articles")
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Erreur sauvegarde news: {e}")
    
    async def aggregate_sentiment(self):
        """Agrège le sentiment par catégorie/ticker."""
        async with get_db_session() as session:
            try:
                # Agrégation du sentiment des dernières 24h
                # TODO: Implémenter l'agrégation SQL
                pass
                
            except Exception as e:
                logger.error(f"Erreur agrégation sentiment: {e}")
    
    async def collect_all_news(self):
        """Collecte toutes les sources de news."""
        tasks = [
            asyncio.create_task(self.fetch_newsapi_articles()),
            asyncio.create_task(self.fetch_twitter_sentiment()),
            asyncio.create_task(self.fetch_rss_feeds()),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_articles = []
        for result in results:
            if isinstance(result, list):
                all_articles.extend(result)
        
        if all_articles:
            await self.save_news_data(all_articles)
            await self.aggregate_sentiment()
    
    async def start_collection(self):
        """Démarre la collecte périodique."""
        self.is_running = True
        logger.info("Démarrage du collecteur de news")
        
        while self.is_running:
            try:
                start_time = asyncio.get_event_loop().time()
                
                await self.collect_all_news()
                
                # Maintien de l'intervalle
                elapsed = asyncio.get_event_loop().time() - start_time
                sleep_time = max(0, self.collection_interval - elapsed)
                
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
            except Exception as e:
                logger.error(f"Erreur boucle news: {e}")
                await asyncio.sleep(60)
    
    async def stop(self):
        """Arrête la collecte."""
        self.is_running = False
        logger.info("Arrêt du collecteur de news")