import type { Metadata, Viewport } from "next";
import "./globals.css";
import { ToastProvider } from "@/components/ui/Toast";
import { DepartmentsProvider } from "@/lib/departmentsContext";
import { GlobalFooter } from "@/components/layout/GlobalFooter";
import { ServiceWorkerRegistrar } from "@/components/ServiceWorkerRegistrar";
import { InstallPrompt } from "@/components/ui/InstallPrompt";
import { SplashScreen } from "@/components/ui/SplashScreen";

export const viewport: Viewport = {
  themeColor: "#0a192f",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export const metadata: Metadata = {
  title: "SPARK",
  description: "Structured Preparation and Readiness Kit",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "SPARK",
  },
  icons: {
    icon: "/favicon.png",
    apple: "/apple-touch-icon.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <head>
        {/* Blocks page content before first paint if splash hasn't been seen yet.
            Runs synchronously — no React, no hydration delay.                    */}
        <script dangerouslySetInnerHTML={{ __html:
          `try{if(!sessionStorage.getItem('spark_splash_seen'))document.documentElement.setAttribute('data-splash','1')}catch(e){}`
        }} />
      </head>
      <body className="h-full antialiased">
        <ToastProvider>
          <DepartmentsProvider>
            <SplashScreen />
            {children}
            <GlobalFooter />
            <ServiceWorkerRegistrar />
            <InstallPrompt />
          </DepartmentsProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
