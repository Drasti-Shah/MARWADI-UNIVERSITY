"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const r = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || "Login failed");
      }
      router.push("/dashboard");
      router.refresh();
    } catch (err: any) {
      setError("❌ " + err.message);
      setBusy(false);
    }
  }

  return (
    <div className="login-body">
      <div className="login-card">
        <div className="login-brand">
          <div className="brand-mark">MU</div>
          <div>
            <div className="login-title">Voice Agent Console</div>
            <div className="login-sub">Marwadi University · Admissions</div>
          </div>
        </div>
        <h2 className="login-h">Sign in</h2>
        <form onSubmit={submit}>
          <label className="lbl">Username</label>
          <input className="input" value={username} autoFocus
                 onChange={(e) => setUsername(e.target.value)} />
          <label className="lbl">Password</label>
          <input className="input" type="password" value={password}
                 onChange={(e) => setPassword(e.target.value)} />
          <button className="btn btn-primary login-btn" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
          <div className="result err" style={{ textAlign: "center" }}>{error}</div>
        </form>
      </div>
    </div>
  );
}
