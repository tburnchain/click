"""저장 최적화 — 압축(zstd)·파티션 관리."""

from gamdap.storage.compression import (
    compress,
    compress_json,
    decompress,
    decompress_json,
    ratio,
    train_dictionary,
)

__all__ = [
    "compress",
    "decompress",
    "compress_json",
    "decompress_json",
    "train_dictionary",
    "ratio",
]
