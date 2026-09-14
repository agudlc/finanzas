from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.categories import router as categories_router
from app.api.routes.settings import router as settings_router
from app.api.routes.transactions import router as transactions_router
from app.rates import RateUnavailable
from app.services.errors import DomainError

app = FastAPI(title="Finanzas")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, error: DomainError):
    return JSONResponse(status_code=error.status_code, content={"detail": error.detail})


@app.exception_handler(RateUnavailable)
async def rate_unavailable_handler(request: Request, error: RateUnavailable):
    return JSONResponse(status_code=404, content={"detail": str(error)})


app.include_router(categories_router, prefix="/api/v1")
app.include_router(transactions_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
