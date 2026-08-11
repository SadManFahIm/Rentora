// Rentora push-notification service worker.
// Receives Web Push events and shows them as native browser notifications;
// clicking one opens the app at the notification's target route.

self.addEventListener("install", () => {
  // Take over immediately so an upgraded worker starts receiving pushes.
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

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
