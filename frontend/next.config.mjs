/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Avatars are user supplied URLs; the app renders them with plain <img> so
  // there is no allowlist to maintain for a demo.
  images: { unoptimized: true },
};

export default nextConfig;
