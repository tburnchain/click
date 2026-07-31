/** TBURN.CLICK 브랜드 심볼 — 클릭 커서(.click) + 불꽃(BURN).
 *  인라인 SVG 라 색상 상속·즉시 렌더되고, 파비콘(public/symbol.svg)과 동일한 형태다. */

type Props = { size?: number; className?: string };

export function Symbol({ size = 28, className }: Props) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} className={className}
         role="img" aria-label="TBURN.CLICK">
      <defs>
        <linearGradient id="tbBg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#2563eb" />
          <stop offset="100%" stopColor="#1e3a8a" />
        </linearGradient>
        <linearGradient id="tbFlame" x1="0.5" y1="1" x2="0.5" y2="0">
          <stop offset="0%" stopColor="#f59e0b" />
          <stop offset="100%" stopColor="#fbbf24" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="15" fill="url(#tbBg)" />
      <path d="M18 11 L18 46.2 L26.8 37.4 L33.4 52.8 L37.8 50.6 L31.2 35.2 L42.2 35.2 Z"
            fill="#ffffff" />
      <path d="M46.5 12.5 C49.6 15.1 51 17.9 50.2 20.8 C49.6 23 47.9 24.4 45.4 24.7
               C47.2 22.3 46.9 20.2 44.6 18.3 C44.9 20.6 44.1 22 42.2 22.6
               C41.3 20 41.8 17.6 43.6 15.4 C44.6 14.2 45.6 13.2 46.5 12.5 Z"
            fill="url(#tbFlame)" />
      <circle cx="52.5" cy="29.5" r="2.2" fill="#fbbf24" />
      <circle cx="47.2" cy="33.4" r="1.4" fill="#fbbf24" opacity="0.8" />
    </svg>
  );
}

/** 심볼 + 워드마크. dark 는 어두운 배경용(.click 강조색만 밝게). */
export function Logo({ size = 28, dark = false }: { size?: number; dark?: boolean }) {
  return (
    <span className="brand">
      <Symbol size={size} />
      <span className="brand-name">
        TBURN<span className={dark ? "brand-dot-dark" : "brand-dot"}>.CLICK</span>
      </span>
    </span>
  );
}

/** 텍스트 전용(푸터 등 좁은 자리). */
export const BRAND = "TBURN.CLICK";
