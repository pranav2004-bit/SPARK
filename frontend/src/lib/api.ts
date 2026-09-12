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
  it: "/it/login",
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

// A 429 here means the gateway's per-IP rate limit on this endpoint was
// hit — it says nothing about whether the refresh token itself is valid.
// Students in the same exam hall/lab commonly share one public IP, and
// with the 15-min access token lifetime every one of them calls this
// endpoint automatically throughout an exam; retrying with backoff (rather
// than immediately treating it as a dead session) is what actually fixes
// the underlying "student force-logged-out mid-exam" bug — see
// gateway/nginx.conf's token_refresh_zone comment for the full story.
const REFRESH_RETRY_ATTEMPTS = 3;

async function refreshAccessToken(refreshToken: string): Promise<string> {
  for (let attempt = 1; attempt <= REFRESH_RETRY_ATTEMPTS; attempt++) {
    try {
      const { data } = await axios.post(`${BASE_URL}/auth/token/refresh/`, {
        refresh: refreshToken,
      });
      return data.access;
    } catch (err) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      if (status !== 429 || attempt === REFRESH_RETRY_ATTEMPTS) {
        throw err;
      }
      // Honor the gateway's advertised Retry-After when present (see
      // nginx.conf's @rate_limit_error block); otherwise back off 1s, 2s.
      const retryAfterHeader = axios.isAxiosError(err)
        ? Number(err.response?.headers?.["retry-after"])
        : NaN;
      const delayMs = Number.isFinite(retryAfterHeader) && retryAfterHeader > 0
        ? retryAfterHeader * 1000
        : attempt * 1000;
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  // Unreachable: the loop above always either returns or throws on its
  // final attempt.
  throw new Error("refreshAccessToken: exhausted retries without resolving");
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
        // When role is unknown (never logged in this session — e.g. a fresh
        // "Get Started" visit that 401s before any auth exists), fall back to
        // whichever portal the user is currently under instead of always
        // defaulting to admin — that previously bounced student-portal visitors
        // to /admin/login.
        const path = window.location.pathname;
        const portalFallback = path.startsWith("/admin") ? "admin"
          : path.startsWith("/super-admin") ? "super_admin"
          : "student";
        window.location.href = LOGIN_REDIRECT_PATHS[role ?? portalFallback] ?? "/login";
        return Promise.reject(err);
      };

      if (!refreshToken) {
        isRefreshing = false;
        return forceLogout(error);
      }

      let newAccess: string;
      try {
        newAccess = await refreshAccessToken(refreshToken);
      } catch (refreshError) {
        if (axios.isAxiosError(refreshError) && refreshError.response?.status === 429) {
          // Still rate-limited after retrying with backoff — fail this one
          // request softly instead of forcing logout. The refresh token may
          // well still be valid; the session stays intact and the next
          // natural retry (autosave, activity-log ping, polling, etc.) can
          // succeed once the shared IP's rate-limit bucket has room again.
          processPendingQueue(refreshError, null);
          isRefreshing = false;
          throw refreshError;
        }
        // Any other failure (400 invalid/blacklisted token, 401, network
        // error) means the refresh token itself is genuinely dead.
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
    // No `response` at all means the request never reached the server —
    // offline, DNS failure, timeout, CORS block — as opposed to a real
    // HTTP error response (4xx/5xx), which has its own message below.
    // Same detection used by the exam page's offline queue
    // (assessmentOfflineQueue.ts's isRetryableNetworkError).
    if (error.response === undefined) {
      return "No internet connection. Please check your network and try again.";
    }
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
