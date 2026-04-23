from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.routers import context, inventory, invoices, recommendations, shops

app = FastAPI(title="Tauke.AI", version="0.2.0")

# Serve uploaded receipt images
Path(settings.image_upload_dir).mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.image_upload_dir), name="uploads")

app.include_router(invoices.router,        prefix="/api")
app.include_router(recommendations.router, prefix="/api")
app.include_router(inventory.router,       prefix="/api")
app.include_router(shops.router,           prefix="/api")
app.include_router(context.router,         prefix="/api")
