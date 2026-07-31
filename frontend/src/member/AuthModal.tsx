import { useState } from "react";
import { memberApi, setToken } from "../auth";

export function AuthModal({ initialMode = "signup", refCode, onClose, onAuthed }: {
  initialMode?: "login" | "signup"; refCode?: string | null;
  onClose: () => void; onAuthed: () => void;
}) {
  const [mode, setMode] = useState<"login" | "signup">(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const r = mode === "signup"
        ? await memberApi.signup({ email, password, display_name: name || undefined, ref: refCode || undefined })
        : await memberApi.login({ email, password });
      setToken(r.token);
      onAuthed();
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <div className="auth-modal">
        <div className="auth-tabs">
          <button className={mode === "signup" ? "on" : ""} onClick={() => setMode("signup")}>회원가입</button>
          <button className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>로그인</button>
        </div>
        <div className="auth-body">
          {mode === "signup" && (
            <div className="auth-free">✨ <b>무료 가입</b> · 카드 등록 없이 바로 시작 · 빌더 제작 시에만 구독</div>
          )}
          {mode === "signup" && refCode && (
            <div className="auth-ref">🎁 추천을 통해 가입합니다 (추천코드 <b>{refCode}</b>)</div>
          )}
          {mode === "signup" && (
            <input placeholder="이름/상호 (선택)" value={name} onChange={(e) => setName(e.target.value)} />
          )}
          <input placeholder="이메일" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input type="password" placeholder="비밀번호 (6자 이상)" value={password}
                 onChange={(e) => setPassword(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && submit()} />
          {err && <div className="auth-err">{err}</div>}
          <button className="auth-submit" onClick={submit} disabled={busy}>
            {busy ? "처리 중…" : mode === "signup" ? "무료로 시작하기" : "로그인"}
          </button>
        </div>
      </div>
    </>
  );
}
