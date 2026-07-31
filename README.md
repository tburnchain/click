# GAMDAP — 글로벌 제휴마케팅 데이터 통합 플랫폼

공식 제휴 API에서 상품·수수료·가격·재고를 수집 → 정규화 → 분류 → 분석하는 엔터프라이즈 코어.
설계 근거: [`제휴마케팅_데이터시스템_설계서.md`](제휴마케팅_데이터시스템_설계서.md) (v3.0)

**구현 범위:** M0(스키마)·M1(쿠팡)·M2(환율·카테고리)·M3(수익성)·M4(FastAPI+React)·M5(CJ·Impact)·**M6(AI Assist 프레임워크)·M7(알림·이력)·M8(분류 엔진)·M9(발견 스캐너)·M11(SaaS 엔타이틀먼트·Stripe)**.

---

## 아키텍처 원칙 (요약)

- **거래성 데이터의 유일한 원천 = 공식 API.** LLM/외부검색은 데이터 원천에서 배제. AI는 관리자가 켜는 플러그형 T3 보조.
- **`products`(실물) ↔ `offers`(네트워크별 조건) 분리**, 모든 수치에 출처·신선도 부착.
- **멱등 수집:** 자연키 UPSERT + 변경분만 이력화(트리거).
- **애그리게이터 우선 편입:** CJ·Impact·Rakuten·Awin·쿠팡… 하나의 API로 다수 머천트 확보.
- **수익성 랭킹은 곱셈적 점수:** `EPC_norm^.5 · 수요^.3 · (1−경쟁)^.2 · 신선도` — 함정 상품 수학적 배제.

---

## 프로젝트 구조

```
affiliate/
├─ migrations/                  # SQL 마이그레이션(0001~0011)
├─ src/gamdap/
│  ├─ config.py · logging.py · cli.py · textvec.py
│  ├─ db/                       # 연결풀 · 마이그레이션 러너
│  ├─ domain/                   # enums · Pydantic 스키마
│  ├─ normalize/                # 수수료 · 통화 · 환율(ECB) · 카테고리 매핑
│  ├─ connectors/               # base · 쿠팡(HMAC) · CJ(GraphQL) · Impact(Basic) · registry
│  ├─ ingest/                   # 정규화 조립 · 멱등 UPSERT · 파이프라인 · 엔티티 해소(§5.4)
│  ├─ analytics/                # 수익성(§8) · 분류 엔진(§18) · 변동 감지(§8.4)
│  ├─ discovery/                # 후보 스코어 · UCB 탐사 · 스캐너(§16)
│  ├─ ai/                       # AI Assist 프레임워크(§7): adapter · registry · router · admin · adapters/
│  ├─ tenancy/                  # SaaS(§19): 엔타이틀먼트 · Stripe 웹훅
│  ├─ api/                      # FastAPI: v1 · admin_ai · discovery · billing · repo · 스키마
│  └─ worker.py                 # Celery 워커·스케줄러(§6.2)
├─ Dockerfile · docker/ · .github/workflows/ci.yml · Makefile   # 배포·CI
├─ frontend/                    # React + Vite + TS 대시보드
│  └─ src/components/           # KpiStrip · FilterBar · OffersTable · ScoreBar · SegmentBadge · OpportunityMap · OpportunitiesFeed
└─ tests/                       # 유닛 테스트 (131 passing)
```

---

## 빠른 시작

### 1) 백엔드 의존성
```bash
python -m venv .venv
source .venv/Scripts/activate      # PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### 2) 인프라 (PostgreSQL + Redis)
```bash
cp .env.example .env               # 값 채우기(각 네트워크 키 등)
docker compose up -d
```

### 3) 마이그레이션 · 환율 · 수집 · 점수
```bash
python -m gamdap.cli migrate                                          # 스키마 생성
python -m gamdap.cli fx-sync --provider ecb                           # 환율 동기화
python -m gamdap.cli ingest  --network coupang_partners --keyword 에어프라이어 --limit 30
python -m gamdap.cli resolve                                          # 엔티티 해소(상품↔오퍼 연결)
python -m gamdap.cli score                                            # 수익성 점수 계산
python -m gamdap.cli classify                                         # 광고상품 분류(세그먼트)
python -m gamdap.cli scan-opportunities                               # 변동 감지(기회 이벤트)
```
> 파이프라인 순서: **수집 → 해소 → 점수 → 분류 → 변동감지**. Celery 워커가 이 순서를 주기 실행(`gamdap.worker`).
> 다른 네트워크: `--network cj_affiliate` / `--network impact` (해당 키 설정 후).

### 4) API 서버
```bash
uvicorn gamdap.api.app:app --app-dir src --port 8000
# → http://localhost:8000/docs (OpenAPI), /api/v1/offers, /api/v1/rankings ...
```

### 5) 프런트엔드 대시보드
```bash
cd frontend
npm install
npm run dev        # 개발: http://localhost:5173 (/api → 8000 프록시)
npm run build      # 프로덕션: dist/ 생성 → FastAPI가 자동 정적 서빙(/)
```

### 6) 테스트
```bash
pytest -q
```

---

## 배포 (Docker · 원커맨드)

전체 스택(Postgres·Redis·API·워커)을 한 번에:
```bash
cp .env.example .env
docker compose up -d --build          # app 은 기동 시 자동 마이그레이션
# → http://localhost:8000  (대시보드 + API + /docs)
```
- **app** 서비스: `entrypoint.sh` 가 DB 대기 → 마이그레이션 → uvicorn(멀티워커). 비루트 실행·헬스체크 내장.
- **worker** 서비스: Celery 워커+beat — 환율/수집/후처리 파이프라인을 스케줄(§6.2) 실행.
- 이미지: 멀티스테이지(node 로 프런트 빌드 → python 런타임에 dist 포함).

`make up` / `make down` / `make migrate` / `make pipeline` 단축 명령 제공([Makefile](Makefile)).

## CI (GitHub Actions)
[.github/workflows/ci.yml](.github/workflows/ci.yml) — push/PR 시:
1. **backend**: ruff 린트 → **실제 Postgres에 마이그레이션 적용(+재실행 멱등성 검증)** → pytest → mypy(비차단)
2. **frontend**: `npm ci && npm run build`
3. **docker**: 이미지 빌드

> CI가 실 Postgres에 마이그레이션을 실행하므로, 로컬 DB 없이도 스키마 E2E가 파이프라인에서 검증된다.

---

## 검증 상태 (이번 빌드에서 실제 확인)

| 항목 | 방법 | 결과 |
|------|------|------|
| 유닛 테스트 | `pytest` (수수료·HMAC·SigV4·발견수학·환율·카테고리·수익성·변동감지·분류·엔티티해소·AI·엔타이틀먼트·Stripe·API·커넥터6종) | ✅ **156 passed** |
| 린트 | `ruff check src tests` | ✅ All checks passed |
| **실 PostgreSQL 17 마이그레이션** | 전용 클러스터에 15파일 적용 + 멱등 재실행 | ✅ **테이블35·트리거2·인덱스76 실생성** |
| **실 DB 파이프라인 E2E** | opendata 라이브수집→해소→점수→분류→변동감지 | ✅ **오퍼37·상품31·이력42·점수37·이벤트5** |
| **실 DB 검색(FTS+트라이그램)** | `websearch_to_tsquery` + `similarity()` | ✅ 'ifone'(오타)→iPhone 매칭 |
| **실 DB AI·발견·SaaS·Stripe 경로** | route→승인 / scan→onboard→UCB / entitlement / webhook sync | ✅ 전 경로 실증 |
| **실 DB API 서버(PgRepo)** | :8030 비데모, 실 데이터 응답 | ✅ 전 엔드포인트 |
| React 대시보드 빌드 | `tsc -b && vite build` (strict) | ✅ 40 modules |
| 커넥터 6종 등록 | coupang·cj·impact·opendata·amazon·clickbank | ✅ 전부 configured |
| 실키 라이브수집(제휴 5종) | 각 네트워크 실 API 키 필요 | ⏳ 키 발급 후 (코드·서명 완성) |
| Docker 이미지 빌드 / CI 실행 | 로컬 docker·git remote 없음 | ⏳ 환경에서 |

> **실 DB 전용 버그 2건이 이 검증에서 발견·수정됨**: 이력 트리거 BEFORE→AFTER(마이그 0014), 발견 스캐너 NULL 캐스팅. 남은 ⏳는 각 제휴사 실 키가 필요한 라이브 수집과 docker/CI 환경뿐.

---

## 부하 안정화 · 대용량 압축 (실 PG 실증)
대량 크롤 호출과 폭증 데이터를 위한 초고도화 계층:
- **레이트리밋(토큰버킷) + 서킷브레이커** ([runtime/limiter.py](src/gamdap/runtime/limiter.py)) — 커넥터별 독립 shaping·장애 격리. 파이프라인에 통합.
- **벌크 UPSERT** ([ingest/upsert.py](src/gamdap/ingest/upsert.py) `bulk_upsert_offers`) — 다중 VALUES 단일 왕복+청킹. 실측 **3,000행 5,737 rows/s (행단위 대비 1.9배, 원격은 왕복지연만큼 확대)**.
- **zstd 압축** ([storage/compression.py](src/gamdap/storage/compression.py)) — 크롤 응답을 zstd로 저장. 실측 **4.47배**(8,274→1,851 bytes). 유사 payload용 zstd 딕셔너리 학습 지원.
- **PG17 lz4 TOAST** — 잔여 JSONB 컬럼 네이티브 압축(대형값 lz4 확인).
- **월 파티션 자동관리** ([db/partitions.py](src/gamdap/db/partitions.py) · CLI `ensure-partitions`) — price_history·로그 무한증가 제어(생성/보존).

## 관리자 · SaaS API
- **AI Assist(§7):** `POST /api/v1/ai/providers`(등록) · `/{id}/capabilities`(역량 토글) · `GET/POST /api/v1/ai/suggestions`(제안 리뷰·승인/반려). T1 불변·제안 격리·승인 게이트·예산 가드.
- **발견(§16):** `GET /api/v1/discovery/candidates` · `/{id}/onboard` · `/next-arm`(UCB).
- **SaaS(§19):** `GET /api/v1/me/entitlements` · `POST /api/v1/billing/stripe/webhook`(서명검증+구독동기화). `X-Api-Key`→테넌트→플랜 엔타이틀먼트, `require_api_key=true` 시 게이트 강제.

## 남은 로드맵
- **AI 어댑터 확장:** OpenAI 호환/로컬 LLM/자체 크롤추적 어댑터(프레임워크·레퍼런스 어댑터는 구현됨)
- **관리자 콘솔 UI:** AI 제공자·제안 리뷰·발견 후보·구독 관리 화면(API는 구현됨)
- **니치 군집 고도화:** HDBSCAN·pgvector ANN(현재는 코사인 임계 그리디·해싱 임베딩 폴백)
- **실측 전환율 학습:** 포스트백 연동 → CVR 베이지안 업데이트(현재는 카테고리 prior)
