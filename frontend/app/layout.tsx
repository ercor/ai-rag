import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI RAG — Document Q&A",
  description: "Ask questions about your documents and get grounded answers with citations.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
