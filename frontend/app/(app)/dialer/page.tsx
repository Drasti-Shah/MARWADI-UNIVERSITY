"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "back"];
const DONE = ["completed", "failed", "busy", "no-answer", "canceled"];

export default function DialerPage() {
  const [num, setNum] = useState("+91");
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [activeSid, setActiveSid] = useState<string | null>(null);
  const [call, setCall] = useState<any>(null);
  const chatRef = useRef<HTMLDivElement>(null);

  const press = (k: string) =>
    setNum((n) => (k === "back" ? n.slice(0, -1) : n + (k === "*" ? "*" : k)));

  // Poll the live transcript while a call is active.
  useEffect(() => {
    if (!activeSid) return;
    let stop = false;
    async function tick() {
      try {
        const c = await api.get(`/api/calls/${activeSid}`);
        if (!stop) setCall(c);
        if (c && DONE.includes(c.status)) return; // call ended -> stop polling
      } catch {}
      if (!stop) setTimeout(tick, 2000);
    }
    tick();
    return () => { stop = true; };
  }, [activeSid]);

  // Auto-scroll the chat as new turns arrive.
  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [call?.transcript?.length]);

  async function call_() {
    if (num.replace(/\D/g, "").length < 8) {
      setResult({ ok: false, msg: "Enter a valid number." });
      return;
    }
    setBusy(true);
    setResult(null);
    setCall(null);
    setActiveSid(null);
    try {
      const r = await api.post("/api/call", { number: num });
      setResult({ ok: true, msg: `✅ Calling ${r.to} — status: ${r.status}` });
      setActiveSid(r.sid);
    } catch (e: any) {
      setResult({ ok: false, msg: `❌ ${e.message}` });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={activeSid ? "grid-2" : ""}>
      <div className="card dialer-card">
        <h2>Place a call</h2>
        <p className="muted">The agent will dial the number and run the Gujarati admission flow.</p>
        <div className="dial-display">{num}</div>
        <div className="keypad">
          {KEYS.map((k) => (
            <button key={k} onClick={() => press(k)}>{k === "back" ? "⌫" : k}</button>
          ))}
        </div>
        <div className="dial-actions">
          <button className="btn btn-primary" onClick={call_} disabled={busy}>📞 Call</button>
          <button className="btn btn-ghost" onClick={() => setNum("+91")}>Clear</button>
        </div>
        {result && <div className={"result " + (result.ok ? "ok" : "err")}>{result.msg}</div>}
      </div>

      {activeSid && (
        <div className="card">
          <div className="card-head">
            <h2>Live conversation</h2>
            <span className={"badge " + (call?.status || "")}>{call?.status || "connecting…"}</span>
          </div>
          <div className="live-status">
            {call?.name ? `${call.name} · ` : ""}{call?.to_number || num}
          </div>
          <div className="live-chat" ref={chatRef}>
            {!call?.transcript?.length ? (
              <div className="muted">Waiting for the conversation to begin…</div>
            ) : call.transcript.map((t: any, i: number) => (
              <div className="turn" key={i}>
                <span className={"who " + t.role}>{t.role === "user" ? "Caller" : "Agent"}</span>
                <div className="txt">
                  <div className="txt-gu">{t.text_gu || t.text}</div>
                  {t.text_gu && t.text && <div className="txt-en">{t.text}</div>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
