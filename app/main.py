"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.routes.auth_routes import router as auth_router

app = FastAPI(title="Commerce-OS e-commerce platform", version="0.1.0")

app.include_router(auth_router)
