from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request

from app.api.routes import (
    followthru,
    health,
    slack_commands,
    slack_interactions,
    workflows,
)
from app.config import settings
from app.logger import configure_logging, logger


def create_app() -> FastAPI:
    configure_logging(settings.log_level)
    app = FastAPI(title=settings.app_name, version=settings.app_version)

    @app.middleware("http")
    async def add_request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        started = perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{perf_counter() - started:.4f}"
        return response

    app.include_router(health.router)
    app.include_router(followthru.router)
    app.include_router(slack_commands.router)
    app.include_router(slack_interactions.router)
    app.include_router(workflows.router)

    logger.info("Application configured for %s", settings.app_env)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8010)