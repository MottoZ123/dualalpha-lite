import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const rawHost = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:5899";
  const host = /^[a-zA-Z0-9.:[\]-]+$/.test(rawHost) ? rawHost : "localhost:5899";
  const protocol = requestHeaders.get("x-forwarded-proto") === "https" ? "https" : host.startsWith("localhost") || host.startsWith("127.0.0.1") ? "http" : "https";
  const origin = `${protocol}://${host}`;
  const title = "股票因子研究工作台 · Stock Factor Workbench";
  const description = "市场全景、条件研判、TX / BS 双轨、因子实验室、训练回测与多市场资料中心。";
  return {
    title,
    description,
    manifest: "/manifest.webmanifest",
    openGraph: { title, description, type: "website", url: origin },
    twitter: { card: "summary", title, description },
  };
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
