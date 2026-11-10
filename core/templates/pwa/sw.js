/* Credit Lifesciences service worker. Version: {{ version }}
   - pages: network first, falling back to a cached copy, then to the offline page
   - static files and images: stale-while-revalidate
   - never touches POST requests, checkout, payments, accounts, the admin or APIs (those must always be live) */
const VERSION = "cl-{{ version }}";
const STATIC_CACHE = VERSION + "-static";
const PAGE_CACHE = VERSION + "-pages";
const OFFLINE_URL = "{% url 'offline' %}";
const NEVER = [/^\/checkout\//, /^\/payments\//, /^\/account\//, /^\/cart\//, /^\/api\//, /^\/admin/, /^\/{{ admin_url }}\//, /^\/invoice\//, /^\/shipping\//];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(PAGE_CACHE).then((c) => c.add(OFFLINE_URL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k)))).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (NEVER.some((re) => re.test(url.pathname))) return;

  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok) { const copy = res.clone(); caches.open(PAGE_CACHE).then((c) => c.put(req, copy)); }
          return res;
        })
        .catch(() => caches.match(req).then((hit) => hit || caches.match(OFFLINE_URL)))
    );
    return;
  }

  if (url.pathname.startsWith("{{ static_url }}") || url.pathname.startsWith("{{ media_url }}")) {
    event.respondWith(
      caches.open(STATIC_CACHE).then((cache) =>
        cache.match(req).then((hit) => {
          const refresh = fetch(req).then((res) => { if (res.ok) cache.put(req, res.clone()); return res; }).catch(() => hit);
          return hit || refresh;
        })
      )
    );
  }
});
