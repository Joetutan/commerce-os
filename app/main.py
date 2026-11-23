"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.routes.auth_routes import router as auth_router
from app.api.routes.catalog_admin_routes import router as catalog_admin_router
from app.api.routes.catalog_routes import router as catalog_router

app = FastAPI(title="Commerce-OS e-commerce platform", version="0.1.0")

app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(catalog_admin_router)
