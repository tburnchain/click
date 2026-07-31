import type { Facet } from "../types";

const SEG_LABEL: Record<string, string> = {
  goldmine: "🟢 금맥", rising: "🔵 신흥", cashcow: "🟡 안정",
  saturated: "🟠 포화", avoid: "🔴 회피",
};

interface Props {
  networkFacets: Facet[];
  segmentFacets: Facet[];
  activeNetwork?: string;
  activeSegment?: string;
  networkName: (code: string) => string;
  onNetwork: (code?: string) => void;
  onSegment: (seg?: string) => void;
}

export function FacetChips({ networkFacets, segmentFacets, activeNetwork, activeSegment, networkName, onNetwork, onSegment }: Props) {
  if (networkFacets.length === 0 && segmentFacets.length === 0) return null;
  return (
    <div className="facets">
      {segmentFacets.length > 0 && (
        <div className="facet-group">
          <span className="facet-label">세그먼트</span>
          {segmentFacets.map((f) => (
            <button key={f.key}
              className={`chip ${activeSegment === f.key ? "chip-on" : ""}`}
              onClick={() => onSegment(activeSegment === f.key ? undefined : f.key)}>
              {SEG_LABEL[f.key] ?? f.key} <em>{f.count}</em>
            </button>
          ))}
        </div>
      )}
      {networkFacets.length > 0 && (
        <div className="facet-group">
          <span className="facet-label">네트워크</span>
          {networkFacets.map((f) => (
            <button key={f.key}
              className={`chip ${activeNetwork === f.key ? "chip-on" : ""}`}
              onClick={() => onNetwork(activeNetwork === f.key ? undefined : f.key)}>
              {networkName(f.key)} <em>{f.count}</em>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
