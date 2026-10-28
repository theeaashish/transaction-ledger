from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint to verify backend service liveness."""
    return {
        "status": "healthy",
    }
