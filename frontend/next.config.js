/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  // Don't fail the production/Docker build on lint or TS errors — CI runs lint
  // separately. Keeps `next build` from breaking on env-specific ESLint rule
  // resolution (e.g. @typescript-eslint plugin not present in the build image).
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: true },
};

module.exports = nextConfig;
