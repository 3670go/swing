from fastapi import FastAPI

from app.internal_api import internal_app

app = FastAPI(
    title="Swing Analyzer AI Processing Unit",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.mount("/internal", internal_app)
