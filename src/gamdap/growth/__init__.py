"""growth — 글로벌 제휴네트워크 통합 위탁 확장 엔진.

구성
  attribution : 멀티터치 귀속(시간감쇠·포지션·마르코프 제거효과·Shapley)
  scoring     : 파트너/인플루언서 성과 스코어링(경험적 베이즈·Wilson·히스테리시스 티어)
  settlement  : 다단계 수익배분·보류·정산(십진 정확 배분)
  fraud       : 부정 트래픽 탐지(엔트로피·포아송·HHI·로버스트 z)
  service     : 위 엔진들을 DB 에 연결하는 오케스트레이션
"""

from gamdap.growth import attribution, fraud, scoring, settlement

__all__ = ["attribution", "fraud", "scoring", "settlement"]
