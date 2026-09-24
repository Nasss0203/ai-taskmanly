from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter()


class InternalHealthResponse(BaseModel):
    status: str
    service: str


@router.get("", response_model=InternalHealthResponse)
async def internal_health() -> InternalHealthResponse:
    return InternalHealthResponse(status="ok", service="Taskmanly AI")
