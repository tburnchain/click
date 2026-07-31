"""글로벌 제휴 네트워크 카탈로그 — 단일 원천(비밀 아님).

이 모듈은 **로그인 자격증명(아이디/비밀번호)을 담지 않는다.** 네트워크의 공개
메타데이터(주소·가입경로·커미션·정산·트래킹 파라미터·공개 레퍼럴 링크)만 보유한다.
회원 개인의 제휴 트래킹 코드는 core.member_affiliate_accounts 에 Fernet 암호화로 저장되며,
로그인 비밀번호는 시스템에 저장하지 않는다(비밀번호 관리자에 보관).

integration:
  - "api"    : GAMDAP 커넥터로 상품 수집까지 자동 연동됨
  - "manual" : 가이드 제공, 회원이 트래킹 코드를 직접 등록해 딥링크 주입에 사용
status:
  - "active"  : 가입/이용 가능
  - "pending" : 심사·가입 진행 중
"""

from __future__ import annotations

from typing import Any

# 각 엔트리는 공개 정보만 포함한다. 자격증명·개인 이메일은 절대 넣지 않는다.
AFFILIATE_NETWORKS: list[dict[str, Any]] = [
    {
        "slug": "coupang_partners", "name": "쿠팡 파트너스", "emoji": "🛒",
        "region": "🇰🇷 한국", "category": "이커머스", "integration": "api", "status": "active",
        "homepage": "https://partners.coupang.com/", "signup_url": "https://partners.coupang.com/",
        "connector_code": "coupang_partners", "tracking_param": "subId",
        "tagline": "국내 최대 이커머스. 링크 생성 간단·카테고리 다양.",
        "commission": "CPS 기본 3% (카테고리·기획전별 상이)",
        "approval": "쿠팡 계정으로 즉시 가입 (심사 간소)",
        "payout": "월 단위, 국내 계좌 정산",
        "referral_url": None, "note": "추천(레퍼럴) 프로그램은 2023.9 종료 · CPS 가입은 정상",
        "cautions": [
            "본인·가족 구매는 수수료 불인정 (부정거래 시 정지)",
            "가격·재고 임의 표기 금지 — 공식 링크/API만 사용",
            "'쿠팡 파트너스 활동으로 수수료를 받습니다' 고지 의무",
        ],
    },
    {
        "slug": "amazon_assoc", "name": "Amazon Associates", "emoji": "📦",
        "region": "🌎 글로벌", "category": "글로벌 마켓", "integration": "api", "status": "active",
        "homepage": "https://affiliate-program.amazon.com/", "signup_url": "https://affiliate-program.amazon.com/",
        "connector_code": "amazon_assoc", "tracking_param": "tag",
        "tagline": "세계 최대 상품 풀. 국가별 스토어(US/JP/EU 등) 개별 가입.",
        "commission": "카테고리별 1~10% (럭셔리뷰티 10%, 가전 2.5% 등)",
        "approval": "가입 후 심사 — 사이트/앱/유튜브 등 채널 필요",
        "payout": "국가별 스토어 개별 정산 (최소 지급액 있음)",
        "referral_url": None, "note": None,
        "cautions": [
            "⚠️ 가입 후 180일 내 3건 이상 적격 판매 없으면 계정 해지",
            "본인 구매 수수료 불가, 이메일/PDF 직접 삽입 금지",
            "가격은 반드시 API로 표기 (수동 표기 금지)",
        ],
    },
    {
        "slug": "clickbank", "name": "ClickBank", "emoji": "🔥",
        "region": "🌎 글로벌 · 디지털", "category": "디지털", "integration": "api", "status": "active",
        "homepage": "https://www.clickbank.com/", "signup_url": "https://accounts.clickbank.com/signup/",
        "connector_code": "clickbank", "tracking_param": "tid",
        "tagline": "디지털·정보성 상품 중심. 높은 수수료(50~75%)와 HopLink.",
        "commission": "CPS 고정/비율, 상당수 50~75%",
        "approval": "무료 가입 (승인 빠름)",
        "payout": "주/격주 지급, 첫 지급 전 세금정보·결제수단 등록",
        "referral_url": None, "note": None,
        "cautions": [
            "일부 국가 가입 제한 — 지원 국가 확인",
            "과장·의학적 효능 광고 주의 (계정 정지 사유)",
            "gravity(인기 지표)만 보지 말고 환불률도 확인",
        ],
    },
    {
        "slug": "cj_affiliate", "name": "CJ Affiliate", "emoji": "🔗",
        "region": "🌎 애그리게이터", "category": "애그리게이터", "integration": "api", "status": "active",
        "homepage": "https://www.cj.com/", "signup_url": "https://signup.cj.com/",
        "connector_code": "cj_affiliate", "tracking_param": "sid",
        "tagline": "수천 개 브랜드를 단일 계정으로. 대형 브랜드 다수.",
        "commission": "광고주(브랜드)별 상이 — 브랜드마다 개별 승인",
        "approval": "웹사이트 필수 — 트래픽·콘텐츠 심사",
        "payout": "월 단위 (최소 $50), 계좌/수표",
        "referral_url": None, "note": None,
        "cautions": [
            "⚠️ 6개월 연속 수수료 0이면 계정 비활성 + 휴면수수료($10) 차감",
            "브랜드마다 별도 신청·승인 필요 (거절될 수 있음)",
            "브랜드 상표 키워드 입찰 등 금지 프로모션 확인",
        ],
    },
    {
        "slug": "impact", "name": "Impact", "emoji": "🤝",
        "region": "🌎 애그리게이터", "category": "애그리게이터", "integration": "api", "status": "active",
        "homepage": "https://impact.com/", "signup_url": "https://impact.com/partners/",
        "connector_code": "impact", "tracking_param": "subId1",
        "tagline": "현대적 파트너십 플랫폼. 브랜드 직접 계약 구조.",
        "commission": "브랜드별 계약 조건 (CPS/CPA)",
        "approval": "파트너 가입 후 브랜드별 캠페인 신청·승인",
        "payout": "브랜드별 최소 지급액·주기 상이",
        "referral_url": None, "note": "Referral Partner Program은 신규 브랜드/퍼블리셔 소개 커미션(별개)",
        "cautions": [
            "브랜드마다 조건·쿠키기간이 다르니 계약서 확인",
            "지급 수단(페이오니아 등) 사전 등록 필요",
            "허위 트래픽·인센티브 트래픽 금지",
        ],
    },
    {
        "slug": "rakuten", "name": "Rakuten Advertising", "emoji": "🎯",
        "region": "🌎 US·JP·글로벌", "category": "애그리게이터", "integration": "manual", "status": "active",
        "homepage": "https://rakutenadvertising.com/", "signup_url": "https://rakutenadvertising.com/",
        "connector_code": None, "tracking_param": "u1",
        "tagline": "미국·일본 강세. 대형 리테일 브랜드 다수.",
        "commission": "광고주별 상이",
        "approval": "웹사이트 필요 — 광고주별 개별 승인",
        "payout": "월 단위 (최소 지급액 있음)",
        "referral_url": None, "note": None,
        "cautions": [
            "승인까지 시간이 걸릴 수 있음",
            "쿠키 기간이 짧은 광고주 존재 — 전환 인정 기간 확인",
            "지역(권역)별 계정이 분리될 수 있음",
        ],
    },
    {
        "slug": "awin", "name": "Awin", "emoji": "🇪🇺",
        "region": "🇪🇺 유럽 강세 · 글로벌", "category": "애그리게이터", "integration": "manual", "status": "pending",
        "homepage": "https://www.awin.com/", "signup_url": "https://www.awin.com/",
        "connector_code": None, "tracking_param": "clickref",
        "tagline": "유럽 최대 애그리게이터. ShareASale 통합.",
        "commission": "광고주별 상이 + 상품 피드 제공",
        "approval": "웹사이트 필요",
        "payout": "월 단위 (최소 £20/€20/$20)",
        "referral_url": None, "note": "초대 코드로 가입 심사 예치금($5) 면제 가능",
        "cautions": [
            "가입 시 심사 예치금 $5 (승인되면 첫 수익에서 환급 · 초대코드 시 면제)",
            "광고주별 개별 가입 승인 필요",
            "브랜드 정책(쿠폰·PPC) 위반 주의",
        ],
    },
    {
        "slug": "linkprice", "name": "링크프라이스 (LinkPrice)", "emoji": "🇰🇷",
        "region": "🇰🇷 한국", "category": "애그리게이터", "integration": "manual", "status": "active",
        "homepage": "https://www.linkprice.com/", "signup_url": "https://ac.linkprice.net/join",
        "connector_code": None, "tracking_param": "a_id",
        "tagline": "국내 다양한 머천트를 한 곳에서. CPC/CPS 혼합.",
        "commission": "머천트별 상이 (CPC 클릭당 / CPS 판매당)",
        "approval": "사이트/채널 등록 후 머천트별 제휴 신청",
        "payout": "월 단위, 국내 계좌",
        "referral_url": None, "note": None,
        "cautions": [
            "머천트마다 승인·수수료가 다르니 개별 확인",
            "부정 클릭·자가 클릭 금지",
            "최소 출금액 확인",
        ],
    },
    {
        "slug": "tenping", "name": "텐핑 (Tenping)", "emoji": "📣",
        "region": "🇰🇷 한국", "category": "CPA·모바일", "integration": "manual", "status": "pending",
        "homepage": "https://tenping.kr/", "signup_url": "https://tenping.kr/",
        "connector_code": None, "tracking_param": "ref",
        "tagline": "앱 설치·구독 같은 행동에도 수익. 모바일 캠페인 강함.",
        "commission": "행동형(앱설치·구독) CPA",
        "approval": "회원가입 후 캠페인 선택",
        "payout": "국내 정산",
        "referral_url": None, "note": "레퍼럴 코드 확인차 재가입 예정(탈퇴 후 48시간 후 가입 가능)",
        "cautions": [
            "캠페인별 조건·정산 기준 확인",
            "부정 유입(자가 클릭·허위 설치) 금지",
        ],
    },
    {
        "slug": "adpick", "name": "애드픽 (Adpick)", "emoji": "🎯",
        "region": "🇰🇷 한국", "category": "CPA·모바일", "integration": "manual", "status": "active",
        "homepage": "https://adpick.co.kr/", "signup_url": "https://adpick.co.kr/",
        "connector_code": None, "tracking_param": "ref",
        "tagline": "앱 설치·구독·체험단까지. 초기 비용 없음. 초보 첫 수익 사례 많음.",
        "commission": "앱설치·구독·체험단 CPA",
        "approval": "회원가입 (초대코드 입력란 있음)",
        "payout": "국내 정산",
        "referral_url": None, "note": None,
        "cautions": [
            "캠페인별 승인 조건 확인",
            "자가 전환·부정 유입 금지",
        ],
    },
    {
        "slug": "adlix", "name": "애드릭스 (Adlix)", "emoji": "📈",
        "region": "🇰🇷 한국", "category": "CPA·모바일", "integration": "manual", "status": "active",
        "homepage": "https://www.adlix.co.kr/", "signup_url": "https://www.adlix.co.kr/",
        "connector_code": None, "tracking_param": "i",
        "tagline": "재택·부업용. 순위 차트로 잘 나가는 캠페인 확인.",
        "commission": "캠페인별 CPA",
        "approval": "홈페이지 회원가입",
        "payout": "국내 정산",
        "referral_url": "https://appu.kr/?i=12519155", "note": None,
        "cautions": [
            "순위 차트는 참고용 — 캠페인 조건 확인",
            "부정 유입 금지",
        ],
    },
    {
        "slug": "ebay_partner", "name": "eBay Partner Network", "emoji": "🏷️",
        "region": "🌎 US·글로벌", "category": "글로벌 마켓", "integration": "manual", "status": "pending",
        "homepage": "https://partnernetwork.ebay.com/", "signup_url": "https://partnernetwork.ebay.com/",
        "connector_code": None, "tracking_param": "customid",
        "tagline": "이베이 상품 홍보→수수료. 아마존과 유사하나 경매·중고 등 상품 폭 넓음.",
        "commission": "카테고리별 (EPN)",
        "approval": "Sign Up 후 심사",
        "payout": "월 단위",
        "referral_url": None, "note": "2008년부터 자체 운영",
        "cautions": [
            "가입 승인 심사 필요",
            "이베이 상품·프로모션 정책 준수",
        ],
    },
    {
        "slug": "digistore24", "name": "Digistore24", "emoji": "🇩🇪",
        "region": "🇪🇺 유럽 · 디지털", "category": "디지털", "integration": "manual", "status": "active",
        "homepage": "https://www.digistore24.com/", "signup_url": "https://www.digistore24.com/",
        "connector_code": None, "tracking_param": "aff",
        "tagline": "유럽 최대 디지털 상품 제휴. 8,500+ 오퍼(44개 분야). 클릭뱅크와 유사.",
        "commission": "디지털 오퍼 고수수료",
        "approval": "Affiliate Sign Up",
        "payout": "주 3회 정산 (빠름)",
        "referral_url": None, "note": None,
        "cautions": [
            "세금 정보 등록 전 지급 보류",
            "오퍼 품질·환불률 확인",
        ],
    },
    {
        "slug": "partnerstack", "name": "PartnerStack", "emoji": "🧩",
        "region": "🌎 글로벌", "category": "B2B·SaaS", "integration": "manual", "status": "active",
        "homepage": "https://partnerstack.com/", "signup_url": "https://partnerstack.com/",
        "connector_code": None, "tracking_param": "ps_partner_key",
        "tagline": "B2B·SaaS 전문. 구독 커미션 매달 반복(recurring).",
        "commission": "구독 리커링 (매월 반복)",
        "approval": "Join as partner",
        "payout": "최소 출금 $5",
        "referral_url": None, "note": None,
        "cautions": [
            "프로그램별 승인 필요",
            "SaaS 채널 적합성 확인",
        ],
    },
    {
        "slug": "flexoffers", "name": "FlexOffers", "emoji": "💠",
        "region": "🌎 글로벌 · 애그리게이터", "category": "애그리게이터", "integration": "manual", "status": "pending",
        "homepage": "https://www.flexoffers.com/", "signup_url": "https://www.flexoffers.com/",
        "connector_code": None, "tracking_param": "subid",
        "tagline": "광고주 12,000+ (삼성·세포라 등). 승인 빠름(24~48h).",
        "commission": "광고주별 상이",
        "approval": "Sign Up (24~48h 승인)",
        "payout": "월 단위",
        "referral_url": None, "note": "가입 완료까지 수일 소요될 수 있음",
        "cautions": [
            "광고주별 개별 승인 필요",
            "지급 수단·세금 정보 등록",
        ],
    },
    {
        "slug": "admitad", "name": "Admitad", "emoji": "🌐",
        "region": "🌎 아시아·유럽", "category": "애그리게이터", "integration": "manual", "status": "active",
        "homepage": "https://www.admitad.com/", "signup_url": "https://www.admitad.com/",
        "connector_code": None, "tracking_param": "subid",
        "tagline": "80,000+ 퍼블리셔. 아시아·유럽 커버 넓음.",
        "commission": "광고주별 CPS/CPA",
        "approval": "Sign Up 후 프로그램 신청",
        "payout": "월 단위",
        "referral_url": "https://www.admitad.com/affiliate-publishers/?ref=nnsjr7fgt5", "note": None,
        "cautions": [
            "프로그램별 개별 승인 필요",
            "지급 수단 등록",
        ],
    },
    {
        "slug": "skimlinks", "name": "Skimlinks", "emoji": "🔗",
        "region": "🌎 글로벌", "category": "자동화 툴", "integration": "manual", "status": "active",
        "homepage": "https://www.skimlinks.com/", "signup_url": "https://www.skimlinks.com/",
        "connector_code": None, "tracking_param": "xcust",
        "tagline": "글 속 상품 링크를 자동으로 제휴 링크로 변환.",
        "commission": "자동 링크 수익 배분",
        "approval": "Sign Up 후 사이트 심사",
        "payout": "월 단위",
        "referral_url": None, "note": None,
        "cautions": [
            "수익 배분율 확인",
            "콘텐츠 정책 준수",
        ],
    },
    {
        "slug": "involve_asia", "name": "Involve Asia", "emoji": "⭐",
        "region": "🌏 아시아", "category": "애그리게이터", "integration": "manual", "status": "active",
        "homepage": "https://involve.asia/", "signup_url": "https://involve.asia/",
        "connector_code": None, "tracking_param": "aff_sub",
        "tagline": "아시아 최대 네트워크. 올리브영·K뷰티 캠페인 풍부(한국인에 유용).",
        "commission": "광고주별 CPS",
        "approval": "Sign Up 후 승인",
        "payout": "정기 정산",
        "referral_url": None, "note": "동남아 중심 캠페인 다수",
        "cautions": [
            "프로그램별 승인 필요",
            "권역별 캠페인 확인",
        ],
    },
    {
        "slug": "jvzoo", "name": "JVZoo", "emoji": "🚀",
        "region": "🌎 글로벌 · 디지털", "category": "디지털", "integration": "manual", "status": "active",
        "homepage": "https://www.jvzoo.com/", "signup_url": "https://www.jvzoo.com/",
        "connector_code": None, "tracking_param": "subid",
        "tagline": "디지털 상품(강의·툴) 마켓. 클릭뱅크형, 수수료 50~100%, 무료가입.",
        "commission": "디지털 50~100%",
        "approval": "무료 가입",
        "payout": "즉시/지연 혼합",
        "referral_url": None, "note": None,
        "cautions": [
            "오퍼 품질·환불률 확인",
            "지급 조건(즉시/지연) 확인",
        ],
    },
    {
        "slug": "sovrn", "name": "Sovrn Commerce (구 VigLink)", "emoji": "⚙️",
        "region": "🌎 글로벌", "category": "자동화 툴", "integration": "manual", "status": "active",
        "homepage": "https://sovrn.com/", "signup_url": "https://platform.sovrn.com/",
        "connector_code": None, "tracking_param": "subid",
        "tagline": "코드 한 줄 삽입 시 기존 링크 자동 제휴화. 무료.",
        "commission": "자동 링크 수익 배분",
        "approval": "무료 가입 · 코드 삽입",
        "payout": "월 단위",
        "referral_url": None, "note": None,
        "cautions": [
            "수익 배분율 확인",
            "사이트 정책 준수",
        ],
    },
    {
        "slug": "partnerize", "name": "Partnerize (구 Pepperjam)", "emoji": "🏢",
        "region": "🌎 엔터프라이즈", "category": "애그리게이터", "integration": "manual", "status": "active",
        "homepage": "https://partnerize.com/", "signup_url": "https://www.ascendpartner.com/affiliate/registration",
        "connector_code": None, "tracking_param": "pubref",
        "tagline": "엔터프라이즈 네트워크. 대형 브랜드 D2C. 솔로엔 다소 무거움.",
        "commission": "브랜드별 계약",
        "approval": "브랜드 초대·계약 중심",
        "payout": "브랜드별 상이",
        "referral_url": None, "note": "브랜드를 추천해 계약하는 방식(일반 추천 링크 아님)",
        "cautions": [
            "솔로 퍼블리셔에겐 무거운 편",
            "브랜드 계약 필요",
        ],
    },
    {
        "slug": "avantlink", "name": "AvantLink", "emoji": "🏔️",
        "region": "🇺🇸 US", "category": "프리미엄·아웃도어", "integration": "manual", "status": "active",
        "homepage": "https://avantlink.com/", "signup_url": "https://www.avantlink.com/signup/",
        "connector_code": None, "tracking_param": "ctc",
        "tagline": "프리미엄 네트워크. REI·파타고니아 등 미국 아웃도어. 심사 有.",
        "commission": "광고주별 CPS",
        "approval": "Sign Up 후 심사 (엄격)",
        "payout": "월 단위",
        "referral_url": None, "note": None,
        "cautions": [
            "심사가 엄격한 편",
            "아웃도어 니치에 적합",
        ],
    },
    {
        "slug": "webgains", "name": "Webgains", "emoji": "🇬🇧",
        "region": "🇪🇺 유럽", "category": "애그리게이터", "integration": "manual", "status": "pending",
        "homepage": "https://webgains.com/", "signup_url": "https://www.webgains.com/public/en/",
        "connector_code": None, "tracking_param": "clickref",
        "tagline": "유럽 중심 네트워크. 광고주 1,800곳.",
        "commission": "광고주별 CPS",
        "approval": "Sign Up 후 심사",
        "payout": "월 단위",
        "referral_url": None, "note": None,
        "cautions": [
            "광고주별 승인 필요",
            "유럽 중심 캠페인",
        ],
    },
]

# 가입 전 공통 주의(모든 네트워크 공통)
COMMON_CAUTIONS: list[str] = [
    "본인/가족/지인 구매로 수수료를 만드는 자기거래는 대부분 금지 → 적발 시 계정 정지·수수료 회수",
    "쿠키 기간(전환 인정 기간)과 최소 지급액·지급 주기를 가입 전 반드시 확인",
    "세금·결제 정보(계좌/페이오니아 등) 등록 전에는 지급이 보류됨",
    "무실적 방치 주의 — Amazon(180일 3건)·CJ(6개월 휴면수수료) 등 계정 정지·차감 규정",
    "각사 약관의 금지 프로모션(스팸, 상표 키워드 입찰, 허위·과장, 인센티브 트래픽) 위반 금지",
    "'제휴 활동으로 수수료를 받는다'는 고지(disclosure)는 법적 의무 (공정위·FTC)",
    "⚠️ 로그인 비밀번호는 GAMDAP에 저장하지 마세요 — 비밀번호 관리자에 보관하고, 발급받은 '트래킹 코드'만 연결하세요",
]


# 네트워크별 실제 취급 오퍼 유형(제품 외 디지털·앱·구독·리드·서비스·쿠폰 포함).
# 대표 오퍼 생성/네트워크 시딩에 사용한다.
OFFER_PROFILES: dict[str, list[str]] = {
    "coupang_partners": ["physical_product", "coupon"],
    "amazon_assoc":     ["physical_product", "digital_product"],
    "ebay_partner":     ["physical_product"],
    "clickbank":        ["digital_product", "subscription"],
    "digistore24":      ["digital_product", "subscription"],
    "jvzoo":            ["digital_product"],
    "cj_affiliate":     ["physical_product", "service", "lead"],
    "impact":           ["physical_product", "subscription", "lead"],
    "rakuten":          ["physical_product", "service"],
    "awin":             ["physical_product", "service", "coupon"],
    "flexoffers":       ["physical_product", "service", "lead"],
    "admitad":          ["physical_product", "app_install", "coupon"],
    "involve_asia":     ["physical_product", "app_install", "coupon"],
    "linkprice":        ["physical_product", "service"],
    "tenping":          ["app_install", "subscription", "lead"],
    "adpick":           ["app_install", "lead", "subscription"],
    "adlix":            ["app_install", "lead"],
    "partnerstack":     ["subscription", "service"],
    "skimlinks":        ["physical_product"],
    "sovrn":            ["physical_product"],
    "partnerize":       ["physical_product", "service"],
    "avantlink":        ["physical_product"],
    "webgains":         ["physical_product", "service"],
}


def offer_types_for(slug: str) -> list[str]:
    return OFFER_PROFILES.get(slug, ["physical_product"])


# 네트워크별 '광고상품 데이터 추출' 요구사항.
# method: keyless(가입·키 불필요) | api(가입+API키) | feed(가입+상품피드) | manual(가입 후 링크 수동)
# needs_api: 상품 카탈로그를 우리 DB로 추출하려면 API/피드 자격증명이 필요한가
# connector_ready: 우리 시스템에 추출 커넥터가 이미 구현되어 있는가(키만 넣으면 라이브)
EXTRACTION: dict[str, dict[str, Any]] = {
    "coupang_partners": {"method": "api", "needs_api": True, "connector_ready": True,
        "api_name": "쿠팡 파트너스 OpenAPI (HMAC 서명)", "credentials": ["ACCESS_KEY", "SECRET_KEY"],
        "note": "가입 후 OpenAPI 키 발급. 우리 커넥터 구현됨 → 키만 입력하면 즉시 라이브 추출."},
    "amazon_assoc": {"method": "api", "needs_api": True, "connector_ready": True,
        "api_name": "Amazon PA-API v5", "credentials": ["ACCESS_KEY", "SECRET_KEY", "PARTNER_TAG"],
        "note": "가입 후 180일 내 3건 판매로 PA-API 잠금 해제 필요. 커넥터 구현됨."},
    "clickbank": {"method": "api", "needs_api": True, "connector_ready": True,
        "api_name": "ClickBank Marketplace API", "credentials": ["DEV_KEY", "CLERK_KEY"],
        "note": "가입 후 API 키 발급. 커넥터 구현됨."},
    "cj_affiliate": {"method": "api", "needs_api": True, "connector_ready": True,
        "api_name": "CJ Developer API (GraphQL/REST)", "credentials": ["PERSONAL_ACCESS_TOKEN", "COMPANY_ID", "WEBSITE_ID(PID)"],
        "note": "가입·브랜드 승인 후 Developer Portal 토큰. 커넥터 구현됨."},
    "impact": {"method": "api", "needs_api": True, "connector_ready": True,
        "api_name": "Impact API", "credentials": ["ACCOUNT_SID", "AUTH_TOKEN", "CATALOG_ID"],
        "note": "가입·브랜드 캠페인 승인 후 카탈로그 API. 커넥터 구현됨."},
    "rakuten": {"method": "api", "needs_api": True, "connector_ready": False,
        "api_name": "Rakuten Advertising API (OAuth)", "credentials": ["CLIENT_ID", "CLIENT_SECRET", "TOKEN"],
        "note": "가입·광고주 승인 후 OAuth. 커넥터 미구현(로드맵)."},
    "awin": {"method": "feed", "needs_api": True, "connector_ready": False,
        "api_name": "Awin API 또는 상품 피드(CSV)", "credentials": ["API_TOKEN", "PUBLISHER_ID"],
        "note": "가입·광고주별 승인 후 API 토큰 또는 상품 피드 URL. 커넥터 미구현."},
    "linkprice": {"method": "feed", "needs_api": True, "connector_ready": False,
        "api_name": "LinkPrice 상품 API/피드", "credentials": ["AFFILIATE_ID", "피드/API 키"],
        "note": "가입·머천트별 제휴 후 상품 피드/API. 커넥터 미구현."},
    "tenping": {"method": "manual", "needs_api": False, "connector_ready": False,
        "api_name": None, "credentials": [],
        "note": "CPA 캠페인 링크 생성 중심 — 상품 카탈로그 API 없음. 가입 후 캠페인 링크 수동 등록."},
    "adpick": {"method": "manual", "needs_api": False, "connector_ready": False,
        "api_name": None, "credentials": [],
        "note": "CPA(앱설치·체험단) 링크 생성 중심. 가입 후 캠페인 링크 수동 등록."},
    "adlix": {"method": "manual", "needs_api": False, "connector_ready": False,
        "api_name": None, "credentials": [],
        "note": "CPA 캠페인. 가입 후 캠페인 링크 수동 등록."},
    "ebay_partner": {"method": "api", "needs_api": True, "connector_ready": False,
        "api_name": "eBay Browse/Finding API + EPN", "credentials": ["APP_ID(OAuth)", "EPN_CAMPAIGN_ID"],
        "note": "가입 승인 후 eBay 개발자 앱 + EPN 캠페인. 커넥터 미구현."},
    "digistore24": {"method": "api", "needs_api": True, "connector_ready": False,
        "api_name": "Digistore24 API", "credentials": ["API_KEY"],
        "note": "가입 후 API 키. 커넥터 미구현."},
    "partnerstack": {"method": "api", "needs_api": True, "connector_ready": False,
        "api_name": "PartnerStack Partner API", "credentials": ["API_KEY"],
        "note": "가입·프로그램 승인 후 API 키(구독 커미션). 커넥터 미구현."},
    "flexoffers": {"method": "api", "needs_api": True, "connector_ready": False,
        "api_name": "FlexOffers API", "credentials": ["API_KEY"],
        "note": "가입 후 API 키. 커넥터 미구현."},
    "admitad": {"method": "api", "needs_api": True, "connector_ready": False,
        "api_name": "Admitad API (OAuth)", "credentials": ["CLIENT_ID", "CLIENT_SECRET"],
        "note": "가입·프로그램 승인 후 OAuth 클라이언트. 커넥터 미구현."},
    "skimlinks": {"method": "api", "needs_api": True, "connector_ready": False,
        "api_name": "Skimlinks Link/Product API + JS", "credentials": ["PUBLISHER_ID", "API_KEY"],
        "note": "가입·사이트 심사 후 자동 링크 JS + Product API. 커넥터 미구현."},
    "involve_asia": {"method": "api", "needs_api": True, "connector_ready": False,
        "api_name": "Involve Asia API", "credentials": ["API_KEY", "SECRET"],
        "note": "가입·승인 후 API 키. 커넥터 미구현."},
    "jvzoo": {"method": "api", "needs_api": True, "connector_ready": False,
        "api_name": "JVZoo API", "credentials": ["API_KEY"],
        "note": "무료 가입 후 API 키. 커넥터 미구현."},
    "sovrn": {"method": "api", "needs_api": True, "connector_ready": False,
        "api_name": "Sovrn(구 VigLink) JS + API", "credentials": ["API_KEY / JS 스니펫"],
        "note": "무료 가입 후 코드 삽입 자동 제휴화 + API. 커넥터 미구현."},
    "partnerize": {"method": "api", "needs_api": True, "connector_ready": False,
        "api_name": "Partnerize API", "credentials": ["USER_API_KEY", "APPLICATION_KEY"],
        "note": "가입·브랜드 계약 후 API. 커넥터 미구현."},
    "avantlink": {"method": "feed", "needs_api": True, "connector_ready": False,
        "api_name": "AvantLink API / 상품 피드", "credentials": ["API_KEY", "AFFILIATE_ID"],
        "note": "가입·엄격 심사 후 API/피드. 커넥터 미구현."},
    "webgains": {"method": "feed", "needs_api": True, "connector_ready": False,
        "api_name": "Webgains API / 피드", "credentials": ["API_KEY", "PUBLISHER_ID"],
        "note": "가입·심사 후 API/피드. 커넥터 미구현."},
}

# 키리스 실 데이터 원천(제휴 네트워크 아님 — 가입·키 불필요, 이미 라이브 추출 중)
KEYLESS_SOURCES: list[dict[str, Any]] = [
    {"slug": "apple_media", "name": "Apple 미디어(iTunes Search)", "emoji": "🍎",
     "method": "keyless", "needs_api": False, "connector_ready": True,
     "note": "인증 불필요 공개 API. 실제 앱·음악·영화·전자책 추출 중(app_install·digital)."},
    {"slug": "opendata", "name": "공개데이터(DummyJSON)", "emoji": "🧪",
     "method": "keyless", "needs_api": False, "connector_ready": True,
     "note": "키 없는 공개 샌드박스. 물리상품 실동작 검증용(수집→분류 end-to-end)."},
]


def extraction_for(slug: str) -> dict[str, Any]:
    return EXTRACTION.get(slug, {"method": "manual", "needs_api": False, "connector_ready": False,
                                 "api_name": None, "credentials": [], "note": ""})


def extraction_summary() -> dict[str, Any]:
    api = [s for s, x in EXTRACTION.items() if x["method"] == "api"]
    feed = [s for s, x in EXTRACTION.items() if x["method"] == "feed"]
    manual = [s for s, x in EXTRACTION.items() if x["method"] == "manual"]
    ready = [s for s, x in EXTRACTION.items() if x["connector_ready"]]
    return {"total_networks": len(AFFILIATE_NETWORKS), "api": len(api), "feed": len(feed),
            "manual": len(manual), "connector_ready": len(ready),
            "connector_ready_slugs": ready, "keyless_sources": len(KEYLESS_SOURCES)}


def list_networks(*, status: str | None = None, integration: str | None = None) -> list[dict[str, Any]]:
    """카탈로그 조회(필터 옵션). 각 네트워크에 데이터 추출 요구사항(extraction)을 부착.
    자격증명 값은 포함하지 않는다(필요한 키의 '이름'만)."""
    rows = AFFILIATE_NETWORKS
    if status:
        rows = [n for n in rows if n["status"] == status]
    if integration:
        rows = [n for n in rows if n["integration"] == integration]
    return [{**n, "extraction": extraction_for(n["slug"])} for n in rows]


def catalog_summary() -> dict[str, int]:
    total = len(AFFILIATE_NETWORKS)
    api = sum(1 for n in AFFILIATE_NETWORKS if n["integration"] == "api")
    pending = sum(1 for n in AFFILIATE_NETWORKS if n["status"] == "pending")
    with_ref = sum(1 for n in AFFILIATE_NETWORKS if n.get("referral_url"))
    return {"total": total, "api": api, "manual": total - api, "pending": pending, "referral": with_ref}
