/** @type {import('next').NextConfig} */

// The browser only ever talks to the Next origin (:3000). We proxy /api/* to
// the FastAPI backend so the session cookie works with no CORS setup.
// Use 127.0.0.1 (not "localhost") so Node doesn't resolve to IPv6 ::1 on
// Windows, where uvicorn listens on IPv4 only.
const BACKEND = process.env.BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
    ];
  },
};

module.exports = nextConfig;
