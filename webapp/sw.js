// Chrome on Android only offers "Install app" to a page that registers a
// service worker with a fetch handler. This is that and nothing more: no
// caching. The app shows live lead data and sends WhatsApp messages and
// email from it — a cache serving yesterday's queue would be worse than an
// error, and there is nothing useful to do offline.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
