// 상품 이미지 공용 폴백 — 썸네일 누락/로드실패 시 회색 빈 박스 대신 깔끔한 플레이스홀더 노출.
export const FALLBACK_IMG =
  "data:image/svg+xml;charset=utf-8," +
  encodeURIComponent(
    "<svg xmlns='http://www.w3.org/2000/svg' width='400' height='400'>" +
    "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>" +
    "<stop offset='0' stop-color='#eef2f7'/><stop offset='1' stop-color='#dfe6ef'/></linearGradient></defs>" +
    "<rect width='400' height='400' fill='url(#g)'/>" +
    "<g fill='none' stroke='#a9b4c4' stroke-width='10' stroke-linejoin='round'>" +
    "<rect x='120' y='140' width='160' height='120' rx='10'/>" +
    "<circle cx='165' cy='180' r='16' fill='#a9b4c4' stroke='none'/>" +
    "<path d='M132 250 L185 205 L220 235 L255 200 L268 250'/></g>" +
    "<text x='200' y='300' text-anchor='middle' font-family='sans-serif' font-size='22' fill='#95a1b2'>이미지 준비중</text>" +
    "</svg>",
  );

// <img onError> 핸들러 — 폴백으로 교체(무한루프 방지)
export function onImgError(e: { currentTarget: HTMLImageElement }): void {
  const el = e.currentTarget;
  if (el.dataset.fb) return;
  el.dataset.fb = "1";
  el.src = FALLBACK_IMG;
}

// 썸네일 URL을 안전하게 반환(null/빈값이면 폴백)
export const thumb = (url?: string | null): string => (url && url.trim() ? url : FALLBACK_IMG);
