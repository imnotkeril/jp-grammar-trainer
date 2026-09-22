import type { Metadata, Viewport } from "next";
import { Figtree, Playfair_Display } from "next/font/google";
import "../styles/globals.css";
import AppHeader from "@/components/AppHeader";
import ServiceWorkerRegister from "@/components/ServiceWorkerRegister";

// Deliberate non-default pairing (not Inter) — an editorial serif for display/headings
// against a warm, friendly UI sans. See globals.css for the paper/ink/hanko-red palette.
const sans = Figtree({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

const display = Playfair_Display({
  subsets: ["latin"],
  weight: ["600", "700"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: "JP Grammar Trainer",
  description: "Personal N3 grammar spaced-retrieval trainer.",
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  themeColor: "#a8391c",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru" className={`${sans.variable} ${display.variable}`}>
      <body className="min-h-screen antialiased">
        <ServiceWorkerRegister />
        <AppHeader />
        {children}
      </body>
    </html>
  );
}
