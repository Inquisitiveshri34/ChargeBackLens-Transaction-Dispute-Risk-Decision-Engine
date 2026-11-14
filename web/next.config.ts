import type { NextConfig } from "next";

// Where the FastAPI server lives. The browser only ever talks to this origin;
// /api/* is forwarded server-side, so no CORS setup is needed in production.
// The value is fixed at build time: change it, then rebuild.
function resolveApiUrl(): string {
  const configured = process.env.API_URL?.trim();
  if (!configured) {
    // On a host there is no API on localhost. Stop the build here rather than
    // ship a site whose every request fails.
    if (process.env.VERCEL) {
      throw new Error(
        "API_URL is not set. Add it in the project's environment variables, set to the public URL of the ChargebackLens API (for example https://chargebacklens-api.onrender.com), then redeploy.",
      );
    }
    return "http://127.0.0.1:8000";
  }
  let parsed: URL;
  try {
    parsed = new URL(configured);
  } catch {
    throw new Error(`API_URL is not a valid URL: "${configured}". It needs the scheme, for example https://chargebacklens-api.onrender.com.`);
  }
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error(`API_URL must start with http:// or https://, got "${configured}".`);
  }
  return parsed.origin;
}

const API_URL = resolveApiUrl();

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
