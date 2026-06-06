import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Marwadi University · Voice Agent Console",
  description: "Admission voice agent admin console",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
