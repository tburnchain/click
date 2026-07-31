"""커넥터 레지스트리 — adapter 코드로 커넥터를 조회."""

from __future__ import annotations

from collections.abc import Callable

from gamdap.connectors.amazon import AmazonConnector
from gamdap.connectors.base import BaseConnector
from gamdap.connectors.cj import CJConnector
from gamdap.connectors.clickbank import ClickBankConnector
from gamdap.connectors.coupang import CoupangConnector
from gamdap.connectors.digistore24 import Digistore24Connector
from gamdap.connectors.impact import ImpactConnector
from gamdap.connectors.itunes import ITunesConnector
from gamdap.connectors.opendata import OpenDataConnector
from gamdap.connectors.travelpayouts import TravelpayoutsConnector

_REGISTRY: dict[str, Callable[[], BaseConnector]] = {}


def register(adapter: str, factory: Callable[[], BaseConnector]) -> None:
    _REGISTRY[adapter] = factory


def get_connector(adapter: str) -> BaseConnector:
    if adapter not in _REGISTRY:
        raise KeyError(f"등록되지 않은 커넥터 adapter: {adapter!r}")
    return _REGISTRY[adapter]()


# 기본 커넥터 등록
register("coupang", CoupangConnector)
register("cj", CJConnector)
register("impact", ImpactConnector)
register("opendata", OpenDataConnector)
register("amazon", AmazonConnector)
register("clickbank", ClickBankConnector)
register("itunes", ITunesConnector)
register("digistore24", Digistore24Connector)
register("travelpayouts", TravelpayoutsConnector)
