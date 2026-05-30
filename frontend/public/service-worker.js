/* Argus PWA Service Worker：
 * - cache-first：assets（圖、css、js）
 * - network-first：API、HTML（離線時用 cache 或 offline fallback）
 * - 不快取 /api/auth、/api/billing/purchase 等敏感變動端點
 */

const CACHE_NAME = "argus-v1";
const CORE_ASSETS = [
  "/",
  "/manifest.webmanifest",
  "/pwa-icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)),
      ),
    ),
  );
  self.clients.claim();
});

function isApi(url) {
  return url.pathname.startsWith("/api/");
}
function isAsset(url) {
  return url.pathname.startsWith("/assets/");
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Asset: cache-first
  if (isAsset(url)) {
    event.respondWith(
      caches.match(req).then(
        (cached) =>
          cached ||
          fetch(req).then((resp) => {
            const copy = resp.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
            return resp;
          }),
      ),
    );
    return;
  }

  // API: network-first（不快取敏感寫入）
  if (isApi(url)) {
    event.respondWith(fetch(req).catch(() => caches.match(req)));
    return;
  }

  // HTML / SPA：network-first，離線 fallback 到 cache 的 /
  event.respondWith(
    fetch(req).catch(() =>
      caches.match(req).then((cached) => cached || caches.match("/")),
    ),
  );
});
