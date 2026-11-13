import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "DocuMind — Document Intelligence", description: "Ask grounded questions about your documents." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
