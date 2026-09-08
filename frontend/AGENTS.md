<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

---

## Portal Layout Patterns

There are **two coexisting layout patterns** in this codebase. Use the correct one for the portal you are working in — do NOT mix them.

### Pattern A — Wrapper Component (Admin + Student portals)

`src/app/admin/` and `src/app/students/` pages do **not** have a `layout.tsx`. Instead, each page file wraps its content in a layout component:

```tsx
// src/app/admin/batch/page.tsx
import AdminLayout from "@/components/layout/AdminLayout";

export default function BatchPage() {
  return (
    <AdminLayout>
      {/* page content */}
    </AdminLayout>
  );
}
```

Components: `src/components/layout/AdminLayout.tsx`, `src/components/layout/StudentLayout.tsx`

### Pattern B — File-based layout.tsx (Super Admin portal)

`src/app/super-admin/` uses Next.js file-based layouts. The sidebar, nav, and chrome live in `src/app/super-admin/layout.tsx` and are automatically applied to every page under that segment — **pages do not import a layout component**.

```tsx
// src/app/super-admin/overview/page.tsx  ← no layout import needed
export default function OverviewPage() {
  return <div>{/* page content only */}</div>;
}
```

Layout file: `src/app/super-admin/layout.tsx`

### Which pattern to use for new pages

| Portal | Pattern | Where to add chrome |
|--------|---------|---------------------|
| `/admin/*` | A — Wrapper component | Wrap page in `<AdminLayout>` |
| `/students/*` | A — Wrapper component | Wrap page in `<StudentLayout>` |
| `/super-admin/*` | B — File-based `layout.tsx` | Edit `layout.tsx`; pages are chrome-free |

**Never add a `layout.tsx` to `src/app/admin/` or `src/app/students/`** — it would double-render the sidebar. **Never add layout wrapper imports to `src/app/super-admin/` pages** — the file-based layout already provides chrome.

### Every portal layout must call `usePortalGuard`

Route protection is split across two layers (added 2026-08-27, fixing a cross-tab bug — see `src/proxy.ts`'s own comment for the full story):

- **`src/proxy.ts`** (Next.js middleware) only does a coarse "is there any session cookie at all" check. It deliberately does **not** check which role the cookie claims — cookies are shared across every tab of the same browser/origin, but a session is genuinely per-tab (`sessionStorage`, see `src/lib/auth-store.ts`), so role-matching at this layer broke simultaneous multi-tab logins (an admin tab and a student tab open side by side would fight over one shared cookie).
- **`src/hooks/usePortalGuard.ts`** does the real per-tab role enforcement, client-side, reading the tab's own `useAuth()` state. **Every portal layout must call it**, or that portal silently has no role protection at all beyond the coarse "logged in as *something*" cookie check:

```tsx
// Pattern A layouts (AdminLayout.tsx, StudentLayout.tsx, ITLayout.tsx)
export function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  usePortalGuard("admin"); // one line, no destructuring needed unless you use `ready`
  ...
}
```

For **Pattern B** (a file-based `layout.tsx` that also wraps its own login page, like `super-admin/layout.tsx`), pass `{ skip: isLoginPage }` — the guard's "redirect to login" direction doesn't apply on the login page itself; that page's own "already logged in, redirect away" check (in `PortalLoginForm.tsx`, or `students/login/page.tsx` for the one login page that doesn't use that shared component) handles the opposite direction instead:

```tsx
const isLoginPage = pathname === "/super-admin/login";
usePortalGuard("super_admin", { skip: isLoginPage });
```

A new portal (a hypothetical `/it/*`-style addition) needs a `usePortalGuard(role)` call in its layout and an "already authenticated, redirect to `PORTAL_HOME[role]`" mount-time check in its login page — see `src/lib/portalRouting.ts` for the shared role/path constants both layers (and `proxy.ts`) read from.

---

## SearchInput — Controlled + Debounced

`src/components/ui/SearchInput.tsx` is a **controlled** component with a **built-in 300 ms debounce**.

Two rules every caller must follow — violating either causes bugs:

1. **Always pass a controlled `value` prop.** The component syncs its display when `value` changes externally (e.g., "Clear filters" resets parent state). Without this the input appears stale after a reset.

2. **Do NOT add a second debounce in the parent.** The component already fires `onChange` after `debounceMs` (default 300 ms). Adding `useRef`/`setTimeout` in the parent doubles the delay and creates stale-closure bugs.

```tsx
const [search, setSearch] = useState("");

<SearchInput
  value={search}
  onChange={(val) => { setSearch(val); setPage(1); }}
  placeholder="Search by name..."
/>
```

---

## Chart Implementation — CSS + SVG (no Recharts)

Recharts is **not** in `package.json`. The "no new npm packages" constraint applies throughout the project. All charts in the Super Admin Analytics tab (`src/app/super-admin/analytics/page.tsx`) are implemented using:

- **Horizontal bar charts** — CSS `div` bars with percentage widths
- **Line/area charts** — SVG `<path>` with gradient `<linearGradient>` fill, gridlines, and data-point `<circle>` elements

Do NOT install Recharts unless `package.json` is explicitly updated in a planned task. If a future task does add Recharts, replace the custom chart implementations in `analytics/page.tsx` for consistency — do not leave both approaches coexisting.

---

## Jest Test Setup

Tests live in `src/tests/`. Configuration is in `jest.config.js` at the frontend root.

Key points:
- `next/server` (Edge Runtime APIs — `NextRequest`, `NextResponse`) must be **fully mocked** in any test file that imports from `next/server`. These APIs do not exist in the Node.js Jest environment.
- `modulePathIgnorePatterns: ["<rootDir>/.next/"]` prevents a haste-map name-collision warning caused by `.next/standalone/package.json` sharing the same `name` field as the root `package.json`.
- **200% Rule:** every test suite must pass with zero failures across **two consecutive runs** before a task is marked complete.
