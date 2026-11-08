import { get, post } from "./api";

// Phone alerts for new leads: this browser subscribes to Web Push with AIMVA's key and tells the server.
export const pushSupported = () => typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
// iPhones only allow push for apps added to the home screen.
export const needsInstall = () => /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.matchMedia("(display-mode: standalone)").matches;

const keyBytes = (b64) => {
  const s = atob(b64.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (b64.length % 4)) % 4));
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
};

export async function currentDevice() {
  if (!pushSupported()) return null;
  const reg = await navigator.serviceWorker.getRegistration();
  return reg ? reg.pushManager.getSubscription() : null;
}

export async function turnOnPhoneAlerts() {
  if (await Notification.requestPermission() !== "granted") throw new Error("Notifications are blocked for AIMVA. Allow them in your browser settings, then try again.");
  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;
  const { key } = await get("/api/alerts/push-key");
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) });
  return post("/api/alerts/devices", sub.toJSON());
}

export async function turnOffPhoneAlerts() {
  const sub = await currentDevice();
  if (!sub) return null;
  const out = await post("/api/alerts/devices/remove", sub.toJSON());
  await sub.unsubscribe();
  return out;
}
