from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
from dotenv import load_dotenv
import os

load_dotenv()

from routers import nuvemshop, analytics, meta, dashboard
from routers import marketing

app = FastAPI(title="Analytics Pro API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(nuvemshop.router, prefix="/api/nuvemshop", tags=["NuvemShop"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Google Analytics"])
app.include_router(meta.router, prefix="/api/meta", tags=["Meta Ads"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(marketing.router, prefix="/api/marketing", tags=["Marketing"])

# Serve frontend
app.mount("/static", StaticFiles(directory="../"), name="static")

@app.get("/")
async def root():
    return FileResponse("../index.html")

@app.get("/marketing")
async def marketing_page():
    return FileResponse("../marketing.html")

@app.get("/api.js")
async def serve_apijs():
    return FileResponse("../api.js")

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
