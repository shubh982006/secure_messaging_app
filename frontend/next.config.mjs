/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Next blocks cross-origin requests to dev resources (/_next/hmr) by default.
  // Opening the dev server on 127.0.0.1 rather than localhost counts as
  // cross-origin, which blocks HMR and leaves the page rendered but never
  // hydrated. Allow both loopback spellings so either URL works in dev.
  allowedDevOrigins: ["localhost", "127.0.0.1", "0.0.0.0"],
  // Avatars are user supplied URLs; the app renders them with plain <img> so
  // there is no allowlist to maintain for a demo.
  images: { unoptimized: true },
  // Don't scatter generated agent files into the repo on every dev boot.
  agentRules: false,
};

export default nextConfig;
