from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime
import pika
import json
import redis
from prometheus_client import Counter, Histogram, generate_latest, REGISTRY
import os
import uuid

app = FastAPI(title="Order Executor Service", version="1.0.0")

# Configuration
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")

# Redis connection
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=6379,
    decode_responses=True
)

# RabbitMQ connection
connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
channel = connection.channel()

# Declare queues
channel.queue_declare(queue='trading_signals', durable=True)
channel.queue_declare(queue='order_execution', durable=True)

# Metrics
orders_processed = Counter('order_executor_orders_processed_total', 'Total orders processed', ['status'])
order_processing_duration = Histogram('order_executor_processing_duration_seconds', 'Order processing duration')
signals_received = Counter('order_executor_signals_received_total', 'Total signals received')

# Models
class Order(BaseModel):
    symbol: str
    side: str  # 'buy' or 'sell'
    quantity: float
    order_type: str = 'market'  # 'market' or 'limit'
    price: float = None
    signal_id: str = None

class OrderResponse(BaseModel):
    order_id: str
    status: str
    message: str
    timestamp: datetime

# Mock order storage (in production, use PostgreSQL)
orders_db = {}

def process_signal(signal_data):
    """Process incoming trading signals"""
    try:
        signals_received.inc()
        
        # Create order from signal
        order = Order(
            symbol=signal_data.get('symbol'),
            side=signal_data.get('action', 'buy'),
            quantity=signal_data.get('quantity', 1.0),
            signal_id=signal_data.get('signal_id')
        )
        
        # Execute order
        order_id = execute_order(order)
        
        print(f"Signal processed and order {order_id} created")
        
    except Exception as e:
        print(f"Error processing signal: {e}")

def execute_order(order: Order) -> str:
    """Execute a trading order"""
    order_id = str(uuid.uuid4())
    
    # Mock order execution (in production, connect to real exchanges)
    order_status = "executed" if order.side == "buy" else "pending"
    
    orders_db[order_id] = {
        "order_id": order_id,
        "symbol": order.symbol,
        "side": order.side,
        "quantity": order.quantity,
        "order_type": order.order_type,
        "price": order.price,
        "status": order_status,
        "signal_id": order.signal_id,
        "timestamp": datetime.now().isoformat()
    }
    
    orders_processed.labels(status=order_status).inc()
    
    return order_id

def callback(ch, method, properties, body):
    """RabbitMQ callback for processing signals"""
    try:
        signal_data = json.loads(body)
        process_signal(signal_data)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"Error processing message: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag)

# Start consuming signals
channel.basic_consume(queue='trading_signals', on_message_callback=callback)

@app.on_event("startup")
async def startup_event():
    """Start RabbitMQ consumer in background"""
    import threading
    thread = threading.Thread(target=lambda: channel.start_consuming())
    thread.daemon = True
    thread.start()

@app.post("/orders", response_model=OrderResponse)
async def create_order(order: Order, background_tasks: BackgroundTasks):
    """Create a new trading order"""
    with order_processing_duration.time():
        try:
            order_id = execute_order(order)
            
            return OrderResponse(
                order_id=order_id,
                status="created",
                message="Order created successfully",
                timestamp=datetime.now()
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

@app.get("/orders")
async def get_orders():
    """Get all orders"""
    return list(orders_db.values())

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    """Get specific order"""
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Order not found")
    return orders_db[order_id]

@app.get("/orders/{order_id}/status")
async def get_order_status(order_id: str):
    """Get order status"""
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"order_id": order_id, "status": orders_db[order_id]["status"]}

@app.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str):
    """Cancel an order"""
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if orders_db[order_id]["status"] == "executed":
        raise HTTPException(status_code=400, detail="Cannot cancel executed order")
    
    orders_db[order_id]["status"] = "cancelled"
    return {"message": "Order cancelled successfully"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "order-executor",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest(REGISTRY)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004) 
