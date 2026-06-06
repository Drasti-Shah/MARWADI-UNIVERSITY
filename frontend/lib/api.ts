// Thin fetch wrapper. All requests hit the Next origin (/api/*) and are proxied
// to FastAPI by next.config.js rewrites, so the session cookie flows naturally.
async function handle(r: Response): Promise<any> {
  if (r.status === 401) {
    if (typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new Error("unauthorized");
  }
  if (!r.ok) {
    const d = await r.json().catch(() => ({} as any));
    throw new Error(d.detail || r.statusText);
  }
  return r.json();
}

export const api = {
  get: (path: string) => fetch(path).then(handle),
  post: (path: string, body?: any) =>
    fetch(path, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    }).then(handle),
  patch: (path: string, body: any) =>
    fetch(path, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(handle),
  del: (path: string) => fetch(path, { method: "DELETE" }).then(handle),
};
