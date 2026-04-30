"""FastAPI application for Moms Verdict.

Serves both the API endpoints and the static frontend files.
"""
from __future__ import annotations

import json
import logging
import pathlib

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import HOST, PORT, CORS_ORIGINS
from backend.models import VerdictRequest, VerdictResponse
from backend.pipeline import load_data, generate_verdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Moms Verdict API",
    description="AI-powered product review synthesizer for Mumzworld",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
ROOT_DIR = pathlib.Path(__file__).parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "moms-verdict"}


@app.get("/api/products")
async def get_products():
    """Return all products in the catalog."""
    products, _ = load_data()
    return {"products": products}


@app.get("/api/products/{product_id}")
async def get_product(product_id: str):
    """Return a single product with its reviews."""
    products, reviews = load_data()
    product = next((p for p in products if p["id"] == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")

    product_reviews = [r for r in reviews if r["product_id"] == product_id]
    return {"product": product, "reviews": product_reviews}


@app.post("/api/verdict", response_model=VerdictResponse)
async def create_verdict(request: VerdictRequest):
    """Generate an AI-powered verdict for a product's reviews.
    
    This is the main endpoint. It:
    1. Loads reviews for the product
    2. Runs the AI synthesis pipeline
    3. Returns a validated, structured verdict
    """
    logger.info(f"Generating verdict for product: {request.product_id}")
    try:
        response = await generate_verdict(request.product_id)
        return response
    except Exception as e:
        logger.error(f"Verdict generation failed: {e}", exc_info=True)
        return VerdictResponse(
            success=False,
            error=f"Internal error: {str(e)}",
        )


# Serve frontend static files
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def serve_frontend():
    """Serve the main frontend page."""
    return FileResponse(str(FRONTEND_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=True)
