import { api } from "./api";
import { env } from "../config/env";

// ============================================================
// PUSH SERVICE — Web Push subscriptions (browser notifications)
// ============================================================

/** Register the service worker that receives push events. */
export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator)) return null;
  try {
    return await navigator.serviceWorker.register("/sw.js");
  } catch {
    return null;
  }
}

/** True when this browser has a live push subscription registered. */
export async function hasPushSubscription(): Promise<boolean> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return false;
  const reg = await registerServiceWorker();
  if (!reg) return false;
  const sub = await reg.pushManager.getSubscription();
  return !!sub;
}

/** Subscribe this browser to push notifications and store it on the backend. */
export async function enablePush(): Promise<boolean> {
  if (!env.VAPID_PUBLIC_KEY) return false;
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return false;

  const reg = await registerServiceWorker();
  if (!reg) return false;

  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    const key = urlBase64ToUint8Array(env.VAPID_PUBLIC_KEY);
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: key as BufferSource,
    });
  }

  const json = sub.toJSON();
  if (!json.endpoint || !json.keys?.auth || !json.keys?.p256dh) return false;

  await api.post<{ status: string }>("/notifications/push/subscribe/", {
    endpoint: json.endpoint,
    auth: json.keys.auth,
    p256dh: json.keys.p256dh,
  });
  return true;
}

/** Unsubscribe this browser and remove the backend subscription. */
export async function disablePush(): Promise<boolean> {
  if (!("serviceWorker" in navigator)) return true;
  const reg = await registerServiceWorker();
  if (!reg) return true;
  const sub = await reg.pushManager.getSubscription();
  if (sub) {
    const endpoint = sub.endpoint;
    await sub.unsubscribe();
    try {
      await api.delete("/notifications/push/subscribe/", { data: { endpoint } });
    } catch {
      // best-effort: the server may already have dropped it
    }
  }
  return true;
}

/** Convert a base64url VAPID public key to the Uint8Array PushManager wants. */
export function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const base64Normalized = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64Normalized);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) output[i] = raw.charCodeAt(i);
  return output;
}

export default {
  registerServiceWorker,
  hasPushSubscription,
  enablePush,
  disablePush,
  urlBase64ToUint8Array,
};
