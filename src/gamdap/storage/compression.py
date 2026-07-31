"""데이터 압축(zstd) — 대량 크롤 payload/이력의 저장 최적화.

zstd(Zstandard, Facebook)는 gzip 대비 유사~더 나은 압축률에 수 배 빠른 속도.
크롤 응답은 구조가 매우 유사 → **zstd 딕셔너리 압축**으로 소형 payload도 큰 폭 절감.

포맷: 매직 1바이트 헤더로 일반/딕셔너리 압축을 구분해 자기서술적(self-describing).
  0x01 = 일반 zstd, 0x02 = 딕셔너리 zstd(뒤 4바이트 dict_id 생략, 저장측이 dict 관리)
"""

from __future__ import annotations

import json
from typing import Any

import zstandard as zstd

_MAGIC_PLAIN = 0x01
_MAGIC_DICT = 0x02
DEFAULT_LEVEL = 10  # 압축률/속도 균형(3~19). 콜드 데이터는 19까지.


def compress(data: bytes, level: int = DEFAULT_LEVEL, dictionary: bytes | None = None) -> bytes:
    """bytes → 압축 bytes(자기서술 헤더 포함)."""
    if dictionary:
        cctx = zstd.ZstdCompressor(level=level, dict_data=zstd.ZstdCompressionDict(dictionary))
        return bytes([_MAGIC_DICT]) + cctx.compress(data)
    cctx = zstd.ZstdCompressor(level=level)
    return bytes([_MAGIC_PLAIN]) + cctx.compress(data)


def decompress(blob: bytes, dictionary: bytes | None = None) -> bytes:
    """압축 bytes → 원본 bytes. 헤더로 딕셔너리 여부 판별."""
    if not blob:
        return b""
    magic, payload = blob[0], blob[1:]
    if magic == _MAGIC_DICT:
        if not dictionary:
            raise ValueError("딕셔너리 압축인데 dictionary 미제공")
        dctx = zstd.ZstdDecompressor(dict_data=zstd.ZstdCompressionDict(dictionary))
        return dctx.decompress(payload)
    dctx = zstd.ZstdDecompressor()
    return dctx.decompress(payload)


def compress_json(obj: Any, level: int = DEFAULT_LEVEL, dictionary: bytes | None = None) -> bytes:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    return compress(raw, level, dictionary)


def decompress_json(blob: bytes, dictionary: bytes | None = None) -> Any:
    return json.loads(decompress(blob, dictionary).decode("utf-8"))


def train_dictionary(samples: list[bytes], dict_size: int = 65536) -> bytes:
    """유사 payload 샘플로 zstd 딕셔너리 학습. 소형·반복 데이터 압축률을 크게 향상."""
    if len(samples) < 7:
        # zstd 학습은 표본이 적으면 실패 → 표본 복제로 최소 요건 충족
        samples = (samples * ((7 // max(len(samples), 1)) + 1))[:max(7, len(samples))]
    d = zstd.train_dictionary(dict_size, samples)
    return d.as_bytes()


def ratio(original: bytes, compressed: bytes) -> float:
    """압축률(원본/압축). 클수록 좋음."""
    return len(original) / max(len(compressed), 1)
