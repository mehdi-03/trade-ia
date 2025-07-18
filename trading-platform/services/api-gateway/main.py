from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx
import redis
import jwt
from prometheus_client import Counter, Histogram, generate_latest, REGISTRY
import os
import time

app = FastAPI(title="Trading Platform API Gateway", version="1.0.0")

# Configuration
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001")
AI_ENGINE_URL = "http://ai-engine:8003"
DATA_INGESTION_URL = "http://data-ingestion:8002"
ORDER_EXECUTOR_URL = "http://order-executor:8004"

# Redis connection
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=6379,
    decode_responses=True
)

# Security
security = HTTPBearer()

# Metrics
request_count = Counter('api_gateway_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
request_duration = Histogram('api_gateway_request_duration_seconds', 'Request duration')

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files for a simple web UI
app.mount("/", StaticFiles(directory="static", html=True), name="static")

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token with auth service"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AUTH_SERVICE_URL}/validate",
                headers={"Authorization": f"Bearer {credentials.credentials}"}
            )
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Authentication failed")

@app.middleware("http")
async def add_metrics(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    request_count.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    request_duration.observe(duration)
    
    return response

# Auth routes
@app.post("/auth/login")
async def login(request: Request):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{AUTH_SERVICE_URL}/login", json=await request.json())
        return response.json()

@app.post("/auth/register")
async def register(request: Request):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{AUTH_SERVICE_URL}/register", json=await request.json())
        return response.json()

@app.get("/auth/validate")
async def validate_token(token_data: dict = Depends(verify_token)):
    return token_data

# AI Engine routes
@app.get("/signals")
async def get_signals(token_data: dict = Depends(verify_token)):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{AI_ENGINE_URL}/signals")
        return response.json()

@app.post("/signals/generate")
async def generate_signals(request: Request, token_data: dict = Depends(verify_token)):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{AI_ENGINE_URL}/signals/generate", json=await request.json())
        return response.json()

# Data routes
@app.get("/market-data")
async def get_market_data(token_data: dict = Depends(verify_token)):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{DATA_INGESTION_URL}/market-data")
        return response.json()

@app.get("/market-data/{symbol}")
async def get_market_data_symbol(symbol: str, token_data: dict = Depends(verify_token)):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{DATA_INGESTION_URL}/market-data/{symbol}")
        return response.json()

# Order routes
@app.get("/orders")
async def get_orders(token_data: dict = Depends(verify_token)):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{ORDER_EXECUTOR_URL}/orders")
        return response.json()

@app.post("/orders")
async def create_order(request: Request, token_data: dict = Depends(verify_token)):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{ORDER_EXECUTOR_URL}/orders", json=await request.json())
        return response.json()

@app.get("/orders/{order_id}")
async def get_order(order_id: str, token_data: dict = Depends(verify_token)):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{ORDER_EXECUTOR_URL}/orders/{order_id}")
        return response.json()

# DeepSeek chat endpoint
@app.post("/chat")
async def chat(request: Request, token_data: dict = Depends(verify_token)):
    """Relay chat messages to the AI engine."""
    payload = await request.json()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{AI_ENGINE_URL}/api/v1/chat",
            json={"message": payload.get("message", "")},
        )
        return resp.json()

# Health check
@app.get("/health")
async def health_check():
    services_status = {}
    
    # Check auth service
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{AUTH_SERVICE_URL}/health")
            services_status["auth-service"] = "healthy" if response.status_code == 200 else "unhealthy"
    except:
        services_status["auth-service"] = "unhealthy"
    
    # Check AI engine
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{AI_ENGINE_URL}/health")
            services_status["ai-engine"] = "healthy" if response.status_code == 200 else "unhealthy"
    except:
        services_status["ai-engine"] = "unhealthy"
    
    return {
        "status": "healthy",
        "service": "api-gateway",
        "services": services_status
    }

@app.get("/metrics")
async def metrics():
    return generate_latest(REGISTRY)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

