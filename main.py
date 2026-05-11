from fastapi import FastAPI, Request
from motor.motor_asyncio import AsyncIOMotorClient

app = FastAPI(title="Medical Intake Voice Agent")

# MongoDB Setup
# client = AsyncIOMotorClient("mongodb://localhost:27017")
# db = client.medical_intake

@app.get("/")
async def root():
    return {"message": "Medical Intake Voice Agent API is running"}

@app.post("/vapi/webhook")
async def vapi_webhook(request: Request):
    # Handle Vapi events (call.started, call.ended, etc.)
    data = await request.json()
    print(f"Received Vapi event: {data.get('type')}")
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
