from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routers import admin, auth, student
from .store import StoreError


app = FastAPI(title="Piano Lesson Booking API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def error_response(status_code: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"ok": False, "error": {"code": code, "message": message}},
        headers=headers,
    )


@app.exception_handler(StoreError)
def handle_store_error(_request: Request, exc: StoreError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message)


@app.exception_handler(HTTPException)
def handle_http_error(_request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return error_response(
            exc.status_code,
            str(exc.detail["code"]),
            str(exc.detail.get("message", "Request failed.")),
            exc.headers,
        )
    return error_response(exc.status_code, "REQUEST_ERROR", str(exc.detail), exc.headers)


@app.exception_handler(RequestValidationError)
def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    message = exc.errors()[0].get("msg", "Invalid request.") if exc.errors() else "Invalid request."
    return error_response(422, "VALIDATION_ERROR", message)


app.include_router(auth.router)
app.include_router(student.router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
