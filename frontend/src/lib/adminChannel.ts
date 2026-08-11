/**
 * adminChannel.ts
 *
 * Cross-tab real-time sync between the Admin portal and the Super-Admin portal
 * using the native BroadcastChannel API (no extra packages).
 *
 * Both portals live in the same origin so they share the same channel.
 * Tabs using sessionStorage for auth are isolated by design, but they can
 * still communicate via BroadcastChannel messages.
 */

export const ADMIN_CHANNEL_NAME = "spark_admin_events";

export type AdminChannelEvent =
  | { type: "ADMIN_UPDATED"; data: { id: string; name: string; is_active: boolean } }
  | { type: "ADMIN_DELETED"; id: string }
  | { type: "ADMIN_PASSWORD_RESET"; id: string }
  | { type: "PROFILE_UPDATED"; id: string; name: string };

/**
 * Fire-and-forget: post an event to every other open tab.
 * Safe to call from SSR contexts (no-ops server-side).
 */
export function broadcastAdminEvent(event: AdminChannelEvent): void {
  if (typeof window === "undefined") return;
  try {
    const ch = new BroadcastChannel(ADMIN_CHANNEL_NAME);
    ch.postMessage(event);
    ch.close();
  } catch {
    // BroadcastChannel unavailable (e.g. certain private-mode browsers) — degrade gracefully.
  }
}

/**
 * Subscribe to admin events from other tabs.
 * Returns a cleanup function — call it in a useEffect cleanup.
 */
export function listenAdminChannel(
  handler: (event: AdminChannelEvent) => void
): () => void {
  if (typeof window === "undefined") return () => {};
  try {
    const ch = new BroadcastChannel(ADMIN_CHANNEL_NAME);
    const listener = (e: MessageEvent) => handler(e.data as AdminChannelEvent);
    ch.addEventListener("message", listener);
    return () => {
      ch.removeEventListener("message", listener);
      ch.close();
    };
  } catch {
    return () => {};
  }
}
