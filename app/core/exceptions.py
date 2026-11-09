import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


logger = logging.getLogger(__name__)


class LLMProviderError(RuntimeError):
    """Base error for failures at the LLM provider boundary."""


class LLMTimeoutError(LLMProviderError):
    pass


class LLMUnavailableError(LLMProviderError):
    pass


class WritingNotDoneError(Exception):
    """Kế hoạch sửa tính năng viết (V4): the result failed the checks twice."""

    def __init__(self, problem: str) -> None:
        super().__init__(problem)
        self.problem = problem


class InvalidLLMResponseError(LLMProviderError):
    pass


class DraftNotDoneError(Exception):
    pass


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(LLMTimeoutError)
    async def handle_llm_timeout(
        request: Request,
        exc: LLMTimeoutError,
    ) -> JSONResponse:
        logger.warning("llm_timeout path=%s", request.url.path)
        return JSONResponse(
            status_code=504,
            content={"detail": "AI provider timed out."},
        )

    @app.exception_handler(LLMUnavailableError)
    async def handle_llm_unavailable(
        request: Request,
        exc: LLMUnavailableError,
    ) -> JSONResponse:
        logger.warning("llm_unavailable path=%s", request.url.path)
        return JSONResponse(
            status_code=503,
            content={"detail": "AI provider is unavailable."},
        )

    @app.exception_handler(WritingNotDoneError)
    async def handle_writing_not_done(
        request: Request,
        exc: WritingNotDoneError,
    ) -> JSONResponse:
        logger.warning("writing_not_done path=%s problem=%s", request.url.path, exc.problem)
        return JSONResponse(
            status_code=422,
            content={"detail": "WRITING_NOT_DONE", "problem": exc.problem},
        )

    @app.exception_handler(DraftNotDoneError)
    async def handle_draft_not_done(
        request: Request,
        exc: DraftNotDoneError,
    ) -> JSONResponse:
        logger.warning("draft_not_done path=%s", request.url.path)
        return JSONResponse(
            status_code=422,
            content={"detail": "DRAFT_NOT_DONE"},
        )

    @app.exception_handler(InvalidLLMResponseError)
    async def handle_invalid_llm_response(
        request: Request,
        exc: InvalidLLMResponseError,
    ) -> JSONResponse:
        logger.warning("invalid_llm_response path=%s", request.url.path)
        return JSONResponse(
            status_code=502,
            content={"detail": "AI provider returned an invalid response."},
        )

    @app.exception_handler(LLMProviderError)
    async def handle_llm_provider_error(
        request: Request,
        exc: LLMProviderError,
    ) -> JSONResponse:
        logger.warning("llm_provider_error path=%s", request.url.path)
        return JSONResponse(
            status_code=502,
            content={"detail": "AI provider request failed."},
        )
