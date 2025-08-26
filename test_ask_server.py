"""
Test FastAPI server for the /ask endpoint
"""

import sys
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add to path for imports
sys.path.append(os.path.dirname(__file__))

from services.api.routes.ask import router as ask_router

app = FastAPI(title="NeuroNews Ask API Test", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the ask router
app.include_router(ask_router)

@app.get("/")
async def root():
    return {"message": "NeuroNews Ask API Test Server", "ask_endpoint": "/ask"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
