// Rentora service worker.
//
// Two responsibilities:
//   1. Web Push — receives push events and shows them as native browser
//      notifications; clicking one opens the app at the notification's route.
//   2. PWA static caching (Phase 12 P0) — a deliberately conservative,
//      versioned cache for same-origin static assets only. API responses,
//      authentication payloads, admin/fraud data and other private traffic
//      are NEVER cached — they always hit the network.

const STATIC_CACHE = "rentora-static-v1";
const PRECACHE_URLS = [
  "/",
  "/manifest.webmanifest",
  "/favicon.svg",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

// ---------------------------------------------------------------------------
// Install / activate
// ---------------------------------------------------------------------------

self.addEventListener("install", (event) => {
  // Take over immediately so an upgraded worker starts receiving pushes and
  // the new build activates promptly (the client shows the update banner).
  self.skipWaiting();
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      // Precache failures (e.g. a build not yet deployed) must not abort install.
      .catch(() => {})
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    Promise.all([
      self.clients.claim(),
      // Remove caches from older versions of this worker only — never touch
      // caches we don't own.
      caches
        .keys()
        .then((keys) =>
          Promise.all(
            keys
              .filter((k) => k.startsWith("rentora-static-") && k !== STATIC_CACHE)
              .map((k) => caches.delete(k))
          )
        ),
    ])
  );
});

// ---------------------------------------------------------------------------
// Fetch — static cache-first, everything private hits the network
// ---------------------------------------------------------------------------

function isStaticAsset(url) {
  return (
    url.origin === self.location.origin &&
    /\.(js|css|png|svg|ico|webp|woff2?|json)$/.test(url.pathname)
  );
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Never cache API/private traffic, and only handle GET.
  if (request.method !== "GET" || url.pathname.startsWith("/api/")) return;

  // Navigations: network-first, fall back to the cached app shell offline.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches
            .open(STATIC_CACHE)
            .then((cache) => cache.put("/", copy))
            .catch(() => {});
          return response;
        })
        .catch(() => caches.match("/").then((cached) => cached || caches.match("/index.html")))
    );
    return;
  }

  // Static assets (Vite build output, icons, manifest): cache-first.
  if (isStaticAsset(url)) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((response) => {
            if (response.ok) {
              const copy = response.clone();
              caches
                .open(STATIC_CACHE)
                .then((cache) => cache.put(request, copy))
                .catch(() => {});
            }
            return response;
          })
      )
    );
  }
});

// ---------------------------------------------------------------------------
// Push + notification clicks (unchanged)
// ---------------------------------------------------------------------------

self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    payload = { title: "Rentora", body: event.data ? event.data.text() : "New update" };
  }

  const title = payload.title || "Rentora";
  const options = {
    body: payload.body || "",
    icon: payload.icon || "/favicon.svg",
    badge: payload.badge || "",
    data: { url: payload.url || "/" },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ("focus" in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      return self.clients.openWindow(targetUrl);
    })
  );
});
