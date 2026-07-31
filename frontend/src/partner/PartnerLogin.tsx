/** 파트너 로그인 — 발급받은 접속 토큰으로 파트너 센터에 들어간다.
 *
 *  파트너 계정은 운영자가 개설하고 접속 토큰을 전달하는 방식이다(자체 가입 아님).
 *  위탁 계약이 선행돼야 하는 구조라, 아무나 가입해 실적을 쌓는 경로를 열지 않는다.
 */

import { useState } from "react";
import { partnerApi, setPartnerToken } from "./api";
import { Logo } from "../Logo";

export function PartnerLogin({ onAuthed }: { onAuthed: () => void }) {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const value = token.trim();
    if (!value) return;
    setBusy(true);
    setError(null);
    setPartnerToken(value);
    try {
      await partnerApi.me(7);
      onAuthed();
    } catch {
      setError("접속 토큰이 올바르지 않거나 만료되었습니다.");
      setBusy(false);
    }
  };

  return (
    <div className="pl-wrap">
      <form className="pl-card" onSubmit={submit}>
        <div className="pl-brand"><Logo size={30} /></div>
        <h1>파트너 센터</h1>
        <p className="pl-sub">
          발급받은 접속 토큰을 입력하세요. 실적·등급·정산 내역을 확인할 수 있습니다.
        </p>
        <label className="pl-label" htmlFor="pl-token">접속 토큰</label>
        <input
          id="pl-token"
          className="pl-input"
          type="password"
          autoComplete="off"
          placeholder="운영팀에서 전달받은 토큰"
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />
        {error && <div className="pl-error">{error}</div>}
        <button className="pl-submit" type="submit" disabled={busy || !token.trim()}>
          {busy ? "확인 중…" : "입장"}
        </button>
        <p className="pl-foot">
          토큰이 없으신가요? 위탁 계약 담당자에게 파트너 개설을 요청하세요.
        </p>
      </form>
    </div>
  );
}
