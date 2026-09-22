"use client";

import { useEffect } from "react";

// PWA offline app-shell caching — ARCHITECTURE.md Phase 4 task 4.5.
// Registers public/sw.js, which caches only static assets + the shell route.
// Dynamic API responses (review sessions, stats, answers) are intentionally never cached —
// out of scope for MVP (offline SRS state would need a real sync strategy).
export default function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;
    // Register after load so the SW never competes with the initial page load for bandwidth.
    const register = () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // Offline caching is a nice-to-have for this personal tool — a failed registration
        // (unsupported browser, blocked storage) should never break the app itself.
      });
    };
    if (document.readyState === "complete") {
      register();
    } else {
      window.addEventListener("load", register, { once: true });
    }
  }, []);

  return null;
}
