/** @type {import('next').NextConfig} */
const nextConfig = {
  // The bundle is served by the Python WebUI as plain files: no Node server at runtime.
  output: 'export',
  // A single-page app is simpler to serve from http.server than per-route HTML files.
  trailingSlash: false,
  images: { unoptimized: true },
  // Relative asset paths keep the bundle working whether it is mounted at / or below a path.
  assetPrefix: undefined,
};

export default nextConfig;
