import type { NextConfig } from "next";

// En producción Vercel enruta /api/py/* a la función Python (ver vercel.json).
// En local se reenvía a uvicorn: `npm run dev:py`.
const nextConfig: NextConfig = {
  async rewrites() {
    if (process.env.NODE_ENV !== "development") return [];
    return [{ source: "/api/py/:path*", destination: "http://127.0.0.1:8000/api/py/:path*" }];
  },
};

export default nextConfig;
