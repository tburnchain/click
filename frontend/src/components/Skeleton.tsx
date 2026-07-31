// 테이블 로딩 스켈레톤
export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="table-wrap">
      <table className="offers-table">
        <tbody>
          {Array.from({ length: rows }).map((_, i) => (
            <tr key={i}>
              {Array.from({ length: 7 }).map((__, j) => (
                <td key={j}><div className="skel" style={{ width: j === 1 ? "80%" : "60%" }} /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
