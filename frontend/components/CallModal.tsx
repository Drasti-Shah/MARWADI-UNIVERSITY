"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fmtTime, fmtDur } from "@/lib/format";

export default function CallModal({ sid, onClose }: { sid: string; onClose: () => void }) {
  const [call, setCall] = useState<any>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get(`/api/calls/${sid}`).then(setCall).catch((e) => setErr(e.message));
  }, [sid]);

  const number = call
    ? (call.direction === "outbound" ? call.to_number : call.from_number)
    : "";
  const title = call ? (call.name || number || "Call detail") : "Call detail";

  return (
    <div className="modal-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal">
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          {err && <div className="result err">{err}</div>}
          {!call && !err && <div className="muted">Loading…</div>}
          {call && (
            <>
              <div className="kv">
                <div><span className="k">Name</span><br /><span className="v">{call.name || "—"}</span></div>
                <div><span className="k">Number</span><br /><span className="v">{number || "—"}</span></div>
                <div><span className="k">Status</span><br /><span className={"badge " + call.status}>{call.status}</span></div>
                <div><span className="k">Duration</span><br /><span className="v">{fmtDur(call.duration)}</span></div>
                <div><span className="k">Direction</span><br /><span className="v">{call.direction}</span></div>
                <div><span className="k">Time</span><br /><span className="v">{fmtTime(call.created_at)}</span></div>
              </div>
              <h4 style={{ margin: "6px 0 12px" }}>Transcript</h4>
              {call.transcript?.length ? call.transcript.map((t: any, i: number) => (
                <div className="turn" key={i}>
                  <span className={"who " + t.role}>{t.role === "user" ? "Caller" : "Agent"}</span>
                  <div className="txt">
                    <div className="txt-gu">{t.text_gu || t.text}</div>
                    {t.text_gu && t.text && <div className="txt-en">{t.text}</div>}
                  </div>
                </div>
              )) : <div className="muted">No transcript captured for this call.</div>}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
