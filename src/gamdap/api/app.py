"""FastAPI 앱 팩토리. REST(v1) + 정적 대시보드 서빙 + CORS."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gamdap import __version__
from gamdap.api.routers.admin_ai import router as admin_ai_router
from gamdap.api.routers.admin_crawl import router as crawl_router
from gamdap.api.routers.billing import router as billing_router
from gamdap.api.routers.discovery import router as discovery_router
from gamdap.api.routers.members import router as members_router
from gamdap.api.routers.v1 import router as v1_router

_FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(
        title="TBURN.CLICK API",
        version=__version__,
        description="글로벌 제휴마케팅 데이터 통합 플랫폼 — 오퍼·랭킹·비교·분석",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 프로덕션은 도메인 화이트리스트로 제한
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    # 데모 모드: DB 없이 실제 엔진 계산 데이터로 대시보드 시연(GAMDAP_DEMO=true)
    import os
    if os.environ.get("GAMDAP_DEMO", "").lower() in ("1", "true", "yes"):
        from gamdap.api.demo import DemoRepo
        from gamdap.api.deps import get_repo
        app.dependency_overrides[get_repo] = lambda: DemoRepo()

    app.include_router(v1_router)
    app.include_router(admin_ai_router)
    app.include_router(crawl_router)
    app.include_router(discovery_router)
    app.include_router(billing_router)
    app.include_router(members_router)

    # 빌드된 프런트가 있으면 정적 서빙 + SPA 폴백(/site/*, /explore 등 클라이언트 라우트)
    if _FRONTEND_DIST.is_dir():
        assets = _FRONTEND_DIST / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")
        index_file = _FRONTEND_DIST / "index.html"

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str) -> FileResponse:
            # API 경로는 위 라우터가 처리; 여기 도달 = 매칭 실패 → 404
            if full_path.startswith(("api/", "openapi", "docs", "redoc", "health")):
                raise HTTPException(404, "not found")
            # 루트 정적파일(symbol.svg, robots.txt, sitemap.xml 등)은 실제 파일로 응답.
            # 없으면 SPA 폴백 — 파비콘이 index.html 로 반환되던 문제 방지.
            if full_path and "/" not in full_path and ".." not in full_path:
                candidate = (_FRONTEND_DIST / full_path).resolve()
                # dist 밖으로 벗어나는 경로는 거부(경로 탐색 차단)
                if candidate.is_file() and candidate.is_relative_to(_FRONTEND_DIST.resolve()):
                    return FileResponse(str(candidate))
            return FileResponse(str(index_file))

    return app


app = create_app()
