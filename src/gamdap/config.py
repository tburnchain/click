"""중앙 설정 — 환경변수(GAMDAP_*)에서 로드. 비밀키는 시크릿매니저 참조 권장."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GAMDAP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = False

    # --- PostgreSQL ---
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "gamdap"
    db_user: str = "gamdap"
    db_password: str = "changeme"
    db_pool_min: int = 2
    db_pool_max: int = 10

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- 통화 ---
    base_currency: str = "KRW"

    # --- 쿠팡 파트너스 ---
    coupang_access_key: str = ""
    coupang_secret_key: str = ""
    coupang_subid: str = ""
    coupang_base_url: str = "https://api-gateway.coupang.com"

    # --- CJ Affiliate (애그리게이터, GraphQL) ---
    cj_token: str = ""              # Developer Portal Personal Access Token
    cj_company_id: str = ""         # publisher company id
    cj_website_id: str = ""         # PID/website id
    cj_base_url: str = "https://ads.api.cj.com"

    # --- Impact (애그리게이터, Basic Auth) ---
    impact_account_sid: str = ""
    impact_auth_token: str = ""
    impact_catalog_id: str = ""
    impact_base_url: str = "https://api.impact.com"

    # --- Amazon Associates (PA-API v5, SigV4) ---
    amazon_access_key: str = ""
    amazon_secret_key: str = ""
    amazon_partner_tag: str = ""
    amazon_region: str = "us-east-1"
    amazon_host: str = "webservices.amazon.com"

    # --- ClickBank (Marketplace API) ---
    clickbank_dev_key: str = ""
    clickbank_clerk_key: str = ""
    clickbank_base_url: str = "https://api.clickbank.com"

    # --- Digistore24 (Marketplace API, 단일 API 키) ---
    digistore24_api_key: str = ""
    digistore24_base_url: str = "https://www.digistore24.com/api/call"

    # --- Travelpayouts (Data API, 단일 토큰) — 공개 여행 카탈로그(실 항공권 특가) ---
    travelpayouts_token: str = ""
    travelpayouts_marker: str = ""  # 제휴 마커(딥링크 수익귀속). 없으면 토큰 검색링크 사용
    travelpayouts_base_url: str = "https://api.travelpayouts.com"

    # --- 공개 데이터(키리스, 실검색 실증) ---
    opendata_base_url: str = "https://dummyjson.com"

    # --- SaaS / Stripe ---
    stripe_webhook_secret: str = ""
    require_api_key: bool = False   # True면 엔타이틀먼트 게이트 강제(멀티테넌트 운영)
    # 회원 인증/자격증명 암호화 마스터 시크릿(프로덕션은 시크릿매니저)
    app_secret: str = "dev-app-secret-change-in-production-please-32b"

    # --- 환율 ---
    fx_provider: Literal["manual", "ecb", "koreaexim"] = "manual"
    fx_api_key: str = ""

    @property
    def db_dsn(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def coupang_configured(self) -> bool:
        return bool(self.coupang_access_key and self.coupang_secret_key)


@lru_cache
def get_settings() -> Settings:
    """프로세스 단위 싱글턴 설정."""
    return Settings()
