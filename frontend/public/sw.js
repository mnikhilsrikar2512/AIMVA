// AIMVA service worker: phone alerts for new leads (Web Push) and the app's install on the home screen.
// It caches nothing on purpose: lead data must always be fresh, and an offline copy would show old leads as new.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {}); // present so browsers treat AIMVA as installable; the network answers

self.addEventListener("push", (e) => {
  let m = {};
  try { m = e.data ? e.data.json() : {}; } catch { m = { title: "AIMVA", body: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(m.title || "New lead", {
    body: m.body || "", tag: m.tag, renotify: true, icon: "/icon-192.png", badge: "/icon-192.png", data: { url: m.url || "/app/leads" },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = new URL(e.notification.data?.url || "/app/leads", self.location.origin).href;
  e.waitUntil((async () => {
    const open = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const tab = open.find((c) => c.url.startsWith(self.location.origin));
    if (tab) { await tab.focus(); return tab.navigate(url); }
    return self.clients.openWindow(url);
  })());
});
