from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import redis
import jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client import REGISTRY
import os

app = FastAPI(title="Auth Service", version="1.0.0")

# Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION = 30  # minutes

# Redis connection
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=6379,
    decode_responses=True
)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security
security = HTTPBearer()

# Metrics
login_attempts = Counter('auth_login_attempts_total', 'Total login attempts', ['status'])
token_validations = Counter('auth_token_validations_total', 'Total token validations', ['status'])
login_duration = Histogram('auth_login_duration_seconds', 'Login duration in seconds')

# Models
class UserLogin(BaseModel):
    username: str
    password: str

class UserRegister(BaseModel):
    username: str
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

# Mock user database (in production, use PostgreSQL)
users_db = {
    "admin": {
        "username": "admin",
        "email": "admin@trading.com",
        "hashed_password": pwd_context.hash("admin123"),
        "role": "admin"
    }
}

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRATION)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/login", response_model=Token)
@login_duration.time()
async def login(user_credentials: UserLogin):
    user = users_db.get(user_credentials.username)
    if not user or not verify_password(user_credentials.password, user["hashed_password"]):
        login_attempts.labels(status="failed").inc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    access_token = create_access_token(data={"sub": user["username"]})
    
    # Store token in Redis for session management
    redis_client.setex(f"token:{access_token}", JWT_EXPIRATION * 60, user["username"])
    
    login_attempts.labels(status="success").inc()
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/register")
async def register(user_data: UserRegister):
    if user_data.username in users_db:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = pwd_context.hash(user_data.password)
    users_db[user_data.username] = {
        "username": user_data.username,
        "email": user_data.email,
        "hashed_password": hashed_password,
        "role": "user"
    }
    
    return {"message": "User registered successfully"}

@app.get("/validate")
async def validate_token(current_user: str = Depends(get_current_user)):
    token_validations.labels(status="valid").inc()
    return {"valid": True, "username": current_user}

@app.post("/logout")
async def logout(current_user: str = Depends(get_current_user)):
    # In a real implementation, you would invalidate the token
    return {"message": "Logged out successfully"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "auth-service"}

@app.get("/metrics")
async def metrics():
    return generate_latest(REGISTRY)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001) 