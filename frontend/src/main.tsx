import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { Landing } from "./member/Landing";
import { MemberDashboard } from "./member/MemberDashboard";
import { SitePage } from "./member/SitePage";
import { getToken, memberApi } from "./auth";
import "./styles.css";

function Root() {
  const path = window.location.pathname;
  const isSite = path.startsWith("/site/");
  const isExplore = path.startsWith("/explore");
  const [authed, setAuthed] = useState<boolean | null>(null);

  // 훅은 조건 없이 최상단에서 호출(React 규칙)
  useEffect(() => {
    if (isSite || isExplore) return;
    if (!getToken()) { setAuthed(false); return; }
    memberApi.me().then(() => setAuthed(true)).catch(() => setAuthed(false));
  }, [isSite, isExplore]);

  if (isSite) return <SitePage path={path} />;
  if (isExplore) return <App />;
  if (authed === null) return <div className="pub-empty">불러오는 중…</div>;
  return authed
    ? <MemberDashboard onLogout={() => window.location.reload()} />
    : <Landing onAuthed={() => window.location.reload()} />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
