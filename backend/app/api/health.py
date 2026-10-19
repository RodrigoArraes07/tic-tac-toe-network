from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.database import ping

router = APIRouter(prefix="/api")


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    if await ping(request.app.state.mongo_client):
        return JSONResponse({"status": "ok", "db": "ok"})
    return JSONResponse(
        {"status": "degraded", "db": "error"},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )
