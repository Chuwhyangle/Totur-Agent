"""Health check API route."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Return basic service status."""

    return {
        "status": "ok",
        "service": "tutor-agent-api",
    }
