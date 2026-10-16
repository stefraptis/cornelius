import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  agentRules: false,
  // Next.js dev blocks its scripts when the page is opened through another
  // origin than localhost (for example the LAN address of this machine). List
  // extra dev origins here or in NEXT_DEV_ORIGINS (comma separated).
  allowedDevOrigins: [
    "192.168.1.42",
    ...(process.env.NEXT_DEV_ORIGINS ?? "").split(",").map((s) => s.trim()).filter(Boolean),
  ],
  poweredByHeader: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
