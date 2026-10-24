import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "知据 · evidence-rag",
  description: "可溯源的团队知识助手（阶段 1 本地演示）",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
