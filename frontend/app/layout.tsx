import type { Metadata } from "next";
import "./globals.css";
import "./realtime.css";

export const metadata: Metadata = {
  title: "JINROID",
  description: "AIが紛れ込む人狼ゲーム",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
