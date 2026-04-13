from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.categories import router as categories_router
from app.api.routes.transactions import router as transactions_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(categories_router, prefix="/api/v1")
app.include_router(transactions_router, prefix="/api/v1")

@app.get("/health")
def health():
    return {"status": "ok"}