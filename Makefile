# GAMDAP 개발 편의 명령
.PHONY: help install up down migrate fx ingest pipeline test lint build fe demo

help:
	@echo "install  - 백엔드 의존성 설치(editable + dev)"
	@echo "up       - docker compose 전체 기동(db·redis·app·worker)"
	@echo "down     - docker compose 종료"
	@echo "migrate  - DB 마이그레이션"
	@echo "fx       - 환율 동기화"
	@echo "ingest   - 쿠팡 수집(예시)"
	@echo "pipeline - 해소→점수→분류→변동감지"
	@echo "test     - pytest"
	@echo "lint     - ruff check"
	@echo "fe       - 프런트 빌드"

install:
	pip install -e ".[dev]"

up:
	docker compose up -d --build

down:
	docker compose down

migrate:
	python -m gamdap.cli migrate

fx:
	python -m gamdap.cli fx-sync --provider ecb

ingest:
	python -m gamdap.cli ingest --network coupang_partners --keyword 에어프라이어 --limit 30

pipeline:
	python -m gamdap.cli resolve
	python -m gamdap.cli score
	python -m gamdap.cli classify
	python -m gamdap.cli scan-opportunities

test:
	pytest -q

lint:
	ruff check src tests

fe:
	cd frontend && npm ci && npm run build

# DB 없이 실제 엔진 계산 데이터로 대시보드 시연 (프런트가 dist에 빌드돼 있어야 함)
demo:
	GAMDAP_DEMO=true GAMDAP_DB_PASSWORD=demo uvicorn gamdap.api.app:app --app-dir src --port 8020
