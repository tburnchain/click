"""경량 텍스트 벡터화 유틸(공용) — M6 임베딩 어댑터·M8 분류에서 재사용.

외부 ML 의존 없이 결정론적 해싱 임베딩 + 코사인 유사도 제공.
대규모 의미검색이 필요하면 이 모듈을 실제 임베딩 모델(pgvector+ANN)로 교체한다.
"""

from __future__ import annotations

import math
import re

_TOKEN = re.compile(r"[0-9a-z가-힣]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def hashing_embedding(text: str, dim: int = 64) -> list[float]:
    """해싱 트릭 기반 TF 임베딩(결정론적, L2 정규화). 같은 텍스트→같은 벡터."""
    vec = [0.0] * dim
    toks = tokenize(text)
    if not toks:
        return vec
    for tok in toks:
        h = hash_token(tok)
        idx = h % dim
        sign = 1.0 if (h >> 31) & 1 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def hash_token(tok: str) -> int:
    """안정적(프로세스 간 동일) 토큰 해시 — FNV-1a 32bit."""
    h = 0x811C9DC5
    for ch in tok.encode("utf-8"):
        h ^= ch
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def softmax(scores: list[float], temperature: float = 1.0) -> list[float]:
    if not scores:
        return []
    t = max(temperature, 1e-6)
    mx = max(scores)
    exps = [math.exp((s - mx) / t) for s in scores]
    total = sum(exps)
    if total == 0:
        return [1.0 / len(scores)] * len(scores)
    return [e / total for e in exps]
