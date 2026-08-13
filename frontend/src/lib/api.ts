import axios, {
  type AxiosInstance,
  type InternalAxiosRequestConfig,
  type AxiosResponse,
} from "axios";
import { useAuthStore } from "./auth-store";
import { clearAuthCookies } from "./cookies";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost/api";

// Exported for regression testing — must stay in sync with useAuth.ts LOGIN_PATHS
// and middleware.ts PORTAL_LOGIN. Any change here requires updating the test.
export const LOGIN_REDIRECT_PATHS: Record<string, string> = {
  student: "/students/login",
  admin: "/admin/login",
  super_admin: "/super-admin/login",
};

// ── Axios instance ──────────────────────────────────────────────────────────────
const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
});

// ── Request interceptor — attach access token ───────────────────────────────────
// Never send an Authorization header on auth endpoints — DRF's JWT middleware
// will reject ANY request that carries an invalid/expired token, even on
// AllowAny views, before permission checking happens.
const NO_AUTH_URLS = ["/login/", "/token/refresh/", "/token/verify/"];

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const url = config.url ?? "";
  const isAuthEndpoint = NO_AUTH_URLS.some((u) => url.includes(u));

  if (!isAuthEndpoint) {
    const token = useAuthStore.getState().accessToken;
    if (token && config.headers) {
      config.headers["Authorization"] = `Bearer ${token}`;
    }
  }
  return config;
});

// ── Response interceptor — refresh on 401 ──────────────────────────────────────
let isRefreshing = false;
let pendingQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
}> = [];

function processPendingQueue(error: unknown, token: string | null) {
  pendingQueue.forEach(({ resolve, reject }) => {
    if (error) reject(error);
    else resolve(token!);
  });
  pendingQueue = [];
}

api.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error) => {
    const originalRequest = error.config;

    // Only attempt refresh on 401, not on the refresh endpoint itself,
    // and only once per request (_retry flag)
    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !originalRequest.url?.includes("token/refresh") &&
      !originalRequest.url?.includes("/login/")
    ) {
      if (isRefreshing) {
        // Queue the request until refresh completes
        return new Promise((resolve, reject) => {
          pendingQueue.push({ resolve, reject });
        }).then((token) => {
          originalRequest.headers["Authorization"] = `Bearer ${token}`;
          return api.request(originalRequest);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const refreshToken = useAuthStore.getState().refreshToken;

      const forceLogout = (err: unknown) => {
        const role = useAuthStore.getState().user?.role;
        useAuthStore.getState().clearAuth();
        clearAuthCookies();
        window.location.href = LOGIN_REDIRECT_PATHS[role ?? "admin"] ?? "/login";
        return Promise.reject(err);
      };

      if (!refreshToken) {
        isRefreshing = false;
        return forceLogout(error);
      }

      let newAccess: string;
      try {
        const { data } = await axios.post(`${BASE_URL}/auth/token/refresh/`, {
          refresh: refreshToken,
        });
        newAccess = data.access;
      } catch (refreshError) {
        // The refresh call itself failed (refresh token invalid/expired,
        // or a network error) — the session is definitively dead.
        processPendingQueue(refreshError, null);
        isRefreshing = false;
        return forceLogout(refreshError);
      }

      useAuthStore.getState().setAccessToken(newAccess);
      processPendingQueue(null, newAccess);
      isRefreshing = false;

      // Retry the original request with the new token. This must be
      // awaited (not `return api(originalRequest)`) — returning the promise
      // unawaited detaches it from this try/catch, so a failure on the
      // retry would silently propagate to the caller instead of being
      // handled below. That was the original bug: a 401 here (e.g. the
      // resource server rejects a token that auth-service just issued as
      // valid — a stale token_version, a deactivated account) left the
      // user stuck on a broken page with a generic error toast and no way
      // back to login short of manually clearing cookies.
      originalRequest.headers["Authorization"] = `Bearer ${newAccess}`;
      try {
        return await api.request(originalRequest);
      } catch (retryError) {
        if (axios.isAxiosError(retryError) && retryError.response?.status === 401) {
          // Refresh succeeded but the freshly-authenticated retry still
          // 401'd — treat as a dead session, same as a failed refresh.
          return forceLogout(retryError);
        }
        // Any other error (500, network, etc.) is not a session problem —
        // propagate it as-is so the caller's normal error handling applies,
        // rather than force-logging the user out over an unrelated failure.
        throw retryError;
      }
    }

    return Promise.reject(error);
  }
);

export default api;

// ── Typed helpers ───────────────────────────────────────────────────────────────

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data;
    if (data?.message) return data.message;
    if (data?.detail) return data.detail;
    if (data?.non_field_errors?.[0]) return data.non_field_errors[0];
    // DRF field errors — return first one
    if (typeof data === "object") {
      const firstKey = Object.keys(data)[0];
      if (firstKey && Array.isArray(data[firstKey])) {
        return `${firstKey}: ${data[firstKey][0]}`;
      }
    }
  }
  if (error instanceof Error) return error.message;
  return "An unexpected error occurred.";
}
