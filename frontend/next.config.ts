import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  devIndicators: false, // hidden for client presentation — restore after
};

export default nextConfig;
