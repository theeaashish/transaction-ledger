from http import HTTPStatus

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.core.exceptions import (
    AppException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from app.main import app

dummy_router = APIRouter(prefix="/test-exceptions", tags=["Testing"])


@dummy_router.get("/not-found")
def trigger_not_found() -> None:
    raise NotFoundException("Ledger entry not found", code="ENTRY_NOT_FOUND")


@dummy_router.get("/conflict")
def trigger_conflict() -> None:
    raise ConflictException("Duplicate reference id", code="DUPLICATE_REFERENCE")


@dummy_router.get("/validation")
def trigger_validation() -> None:
    raise ValidationException("Invalid debit/credit balance", code="UNBALANCED_ENTRY")


@dummy_router.get("/forbidden")
def trigger_forbidden() -> None:
    raise ForbiddenException("Access denied to ledger book", code="ACCESS_DENIED")


@dummy_router.get("/custom")
def trigger_custom() -> None:
    raise AppException(
        "Custom app error",
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        code="CUSTOM_ERR",
    )


@dummy_router.get("/unhandled")
def trigger_unhandled() -> None:
    raise RuntimeError("Unexpected failure")


# Include the test router temporarily
app.include_router(dummy_router)


def test_not_found_exception(client: TestClient) -> None:
    response = client.get("/test-exceptions/not-found")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "ENTRY_NOT_FOUND"
    assert data["error"]["message"] == "Ledger entry not found"


def test_conflict_exception(client: TestClient) -> None:
    response = client.get("/test-exceptions/conflict")
    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "DUPLICATE_REFERENCE"
    assert data["error"]["message"] == "Duplicate reference id"


def test_validation_exception(client: TestClient) -> None:
    response = client.get("/test-exceptions/validation")
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "UNBALANCED_ENTRY"
    assert data["error"]["message"] == "Invalid debit/credit balance"


def test_forbidden_exception(client: TestClient) -> None:
    response = client.get("/test-exceptions/forbidden")
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "ACCESS_DENIED"
    assert data["error"]["message"] == "Access denied to ledger book"


def test_custom_exception(client: TestClient) -> None:
    response = client.get("/test-exceptions/custom")
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "CUSTOM_ERR"
    assert data["error"]["message"] == "Custom app error"


def test_unhandled_exception(client: TestClient) -> None:
    response = client.get("/test-exceptions/unhandled")
    assert response.status_code == 500
    data = response.json()
    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert data["error"]["message"] == "Internal server error"


def test_starlette_method_not_allowed(client: TestClient) -> None:
    response = client.post("/health")
    assert response.status_code == 405
    data = response.json()
    assert data["error"]["code"] == "METHOD_NOT_ALLOWED"
