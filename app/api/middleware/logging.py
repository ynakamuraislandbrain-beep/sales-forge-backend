import time
import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

class LoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        structlog.contextvars.clear_contextvars()
        
        request_id = request.headers.get("X-Request-ID", "")
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            ip=request.client.host if request.client else None,
        )

        start_time = time.perf_counter()
        
        try:
            response = await call_next(request)
            
            process_time = time.perf_counter() - start_time
            
            log_level = logger.info
            if response.status_code >= 500:
                log_level = logger.error
            elif response.status_code >= 400:
                log_level = logger.warning

            log_level(
                "Request finished",
                status_code=response.status_code,
                duration=f"{process_time:.4f}s",
            )
            
            return response

        except Exception as e:
            process_time = time.perf_counter() - start_time
            logger.exception(
                "Request failed",
                error=str(e),
                duration=f"{process_time:.4f}s",
            )
            raise