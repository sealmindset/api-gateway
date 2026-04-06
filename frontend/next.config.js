/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/api/kong/:path*',
        destination: `${process.env.KONG_ADMIN_URL || 'http://kong:8001'}/:path*`,
      },
      {
        source: '/api/:path*',
        destination: `${process.env.ADMIN_API_URL || 'http://admin-panel:8080'}/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
