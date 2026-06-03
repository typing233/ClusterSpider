import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from clusterspider.config import settings
from clusterspider.graph.driver import get_driver, close_driver
from clusterspider.graph.schema import init_schema

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting ClusterSpider API")

    driver = await get_driver()
    await init_schema(driver)
    logger.info("Neo4j schema initialized")

    yield

    await close_driver()
    logger.info("ClusterSpider API shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="ClusterSpider OSINT Platform",
        version="0.2.0",
        description="OSINT Aggregation & Graph Analysis API",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from clusterspider.api.routers import auth, users, scans, graph, reports
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
    app.include_router(scans.router, prefix="/api/v1/scans", tags=["scans"])
    app.include_router(graph.router, prefix="/api/v1/graph", tags=["graph"])
    app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok", "version": "0.2.0"}

    @app.get("/api/v1/modules")
    async def list_modules():
        from clusterspider.modules import ALL_MODULES
        return [{"name": m().name, "description": m().description} for m in ALL_MODULES]

    return app
