"""수집 파이프라인(Bronze→Silver): 정규화·멱등 UPSERT·작업 로깅."""

from gamdap.ingest.pipeline import run_ingestion

__all__ = ["run_ingestion"]
