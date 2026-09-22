// Minimal offline app-shell service worker — ARCHITECTURE.md Phase 4 task 4.5.
// Scope: cache the Next.js static build output + PWA icons/manifest + the shell route so the
// app can install and open offline. Deliberately does NOT cache API responses (review
// sessions, answers, stats) — those are dynamic single-user SRS state; caching them is out
// of scope for MVP and would risk serving stale due-counts/progress.

const CACHE_NAME = "jp-grammar-shell-v1";
const APP_SHELL = ["/", "/manifest.webmanifest", "/icons/icon-192.png", "/icons/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .catch(() => {
        // Best-effort — a partial precache still lets the runtime fetch handler below
        // fill in the rest as the user navigates.
      })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only ever handle same-origin GETs. Cross-origin requests are the backend API
  // (NEXT_PUBLIC_API_BASE_URL) — never intercept those, always hit the network.
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  const isStaticAsset =
    url.pathname.startsWith("/_next/static/") ||
    url.pathname.startsWith("/icons/") ||
    url.pathname === "/manifest.webmanifest";

  if (isStaticAsset) {
    // Cache-first: static build assets are content-hashed by Next.js, safe to serve stale.
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((response) => {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
            return response;
          })
      )
    );
    return;
  }

  if (request.mode === "navigate") {
    // Network-first for page navigations so the owner always sees fresh due-counts when
    // online; falls back to the cached shell only when actually offline.
    event.respondWith(
      fetch(request).catch(() => caches.match(request).then((cached) => cached || caches.match("/")))
    );
  }
});
