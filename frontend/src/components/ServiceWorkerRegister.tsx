"use client";

import { useEffect } from "react";

// PWA offline app-shell caching — ARCHITECTURE.md Phase 4 task 4.5.
// Registers public/sw.js, which caches only static assets + the shell route.
// Dynamic API responses (review sessions, stats, answers) are intentionally never cached —
// out of scope for MVP (offline SRS state would need a real sync strategy).
export default function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;
    // The SW's cache-first strategy for /_next/static/* is only safe against a `next build`
    // output, where those chunks are content-hashed (ARCHITECTURE.md Phase 4 task 4.5 / the
    // comment in public/sw.js). `next dev` does not give the same guarantee, so registering
    // it in dev caches a JS bundle that can go stale on the very next recompile — discovered
    // during QA as a real, reproducible React hydration mismatch after a dev-server restart.
    // Production behavior (the only place this matters) is unaffected.
    if (process.env.NODE_ENV !== "production") return;
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
