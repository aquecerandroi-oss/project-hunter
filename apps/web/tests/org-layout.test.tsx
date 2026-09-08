import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const { resolveOrgContextMock, getServerSessionMock, readyMock } = vi.hoisted(() => ({
  resolveOrgContextMock: vi.fn(),
  getServerSessionMock: vi.fn(),
  readyMock: vi.fn(),
}));

vi.mock("@/lib/api/org-context", () => ({ resolveOrgContext: resolveOrgContextMock }));
vi.mock("@/lib/server/auth", () => ({ getServerSession: getServerSessionMock }));
// `wasReadyCheckAttempted` is real, pure logic -- `vi.importActual` keeps it
// wired to whatever `readyMock` resolves to (same pattern as `dashboard-page.test.tsx`).
vi.mock("@/lib/api/system", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/system")>("@/lib/api/system");
  return { ...actual, ready: readyMock };
});
// `Topbar` is itself an `async function` Server Component -- real RSC
// rendering (Next.js) awaits it before ever handing JSX to the client, but
// `@testing-library/react`'s plain `react-dom` client renderer cannot: an
// async component nested as JSX (not itself `await`-ed, unlike this file's
// own top-level `OrgLayout(...)` call) renders as an unhandled Promise and
// silently blanks the ENTIRE tree (no error boundary here to contain it) --
// `topbar.test.tsx` already covers `Topbar`'s own behaviour by awaiting it
// directly; this file only needs to prove `OrgLayout`'s own branching
// (banner vs. children, redirect/notFound, nav items), so a synchronous
// stub stands in for it here.
vi.mock("@/components/layout/topbar", () => ({
  Topbar: ({ children }: { children?: ReactNode }) => <div data-testid="topbar-stub">{children}</div>,
}));
vi.mock("next/headers", () => ({ headers: async () => ({ get: () => null }) }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
  redirect: (url: string) => {
    throw new Error(`NEXT_REDIRECT:${url}`);
  },
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
  usePathname: () => "/acme/dashboard",
  useParams: () => ({ orgSlug: "acme" }),
}));

import OrgLayout from "@/app/(app)/[orgSlug]/layout";
import { ApiError } from "@/lib/api-error";
import type { MembershipOut } from "@/lib/api/types";

function apiError(status: number, detail: string): ApiError {
  return new ApiError({ type: "about:blank", title: "Error", status, detail });
}

const membership: MembershipOut = {
  onboarding: { completed: true, completed_at: "2026-01-01T00:00:00Z", workspace_id: "ws-1" },
  organization: {
    id: "org-1",
    slug: "acme",
    name: "Acme Capital",
    plan: "FREE",
    kill_switch_state: "ACTIVE",
    created_at: "2026-01-01T00:00:00Z",
  },
  role: "OWNER",
  status: "active",
};

function renderLayout() {
  return OrgLayout({
    children: <div>PAGE CONTENT</div>,
    params: Promise.resolve({ orgSlug: "acme" }),
  });
}

beforeEach(() => {
  getServerSessionMock.mockReset().mockResolvedValue({ userId: "user-1", token: "tok" });
  resolveOrgContextMock.mockReset().mockResolvedValue(membership);
  readyMock.mockReset().mockResolvedValue({ database: true, redis: true });
});

afterEach(cleanup);

describe("OrgLayout: a recoverable /me failure renders the shell, never Next's bare error screen (brief T3.28b)", () => {
  it("shows the honest rate-limit banner and keeps the sidebar/nav usable when /me answers 429", async () => {
    resolveOrgContextMock.mockRejectedValue(apiError(429, "Rate limit exceeded."));

    const jsx = await renderLayout();
    render(jsx);

    expect(screen.getByText(/O servidor limitou as requisições por um instante/)).toBeInTheDocument();
    // The shell (sidebar) is still there -- navigation stays usable.
    expect(screen.getAllByRole("link", { name: /Dashboard/ }).length).toBeGreaterThan(0);
    // The page's own content never rendered -- the layout degraded instead.
    expect(screen.queryByText("PAGE CONTENT")).not.toBeInTheDocument();
  });

  it("shows the generic 'Serviço indisponível' banner for a 503, with the shell still up", async () => {
    resolveOrgContextMock.mockRejectedValue(apiError(503, "downstream unavailable"));

    const jsx = await renderLayout();
    render(jsx);

    expect(screen.getByText("Serviço indisponível.")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Dashboard/ }).length).toBeGreaterThan(0);
  });

  it("shows the same honest banner for a plain network failure (not an ApiError at all)", async () => {
    resolveOrgContextMock.mockRejectedValue(new TypeError("fetch failed"));

    const jsx = await renderLayout();
    render(jsx);

    expect(screen.getByText("Serviço indisponível.")).toBeInTheDocument();
  });
});

describe("OrgLayout: 401/403 from /me keep the existing sign-in redirect, never a degraded banner (brief T3.28b)", () => {
  it("redirects to /sign-in on 401", async () => {
    resolveOrgContextMock.mockRejectedValue(apiError(401, "token expired"));
    await expect(renderLayout()).rejects.toThrow("NEXT_REDIRECT:/sign-in");
  });

  it("redirects to /sign-in on 403", async () => {
    resolveOrgContextMock.mockRejectedValue(apiError(403, "forbidden"));
    await expect(renderLayout()).rejects.toThrow("NEXT_REDIRECT:/sign-in");
  });
});

describe("OrgLayout: unaffected paths keep behaving exactly as before (regression)", () => {
  it("renders the page's own children when /me succeeds", async () => {
    const jsx = await renderLayout();
    render(jsx);

    expect(screen.getByText("PAGE CONTENT")).toBeInTheDocument();
    expect(screen.queryByText(/indisponível/)).not.toBeInTheDocument();
  });

  it("still calls notFound() for a slug with no real membership (never confused with a degraded fetch)", async () => {
    resolveOrgContextMock.mockResolvedValue(null);
    await expect(renderLayout()).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("still redirects to /sign-in when there is no session at all", async () => {
    getServerSessionMock.mockResolvedValue(null);
    await expect(renderLayout()).rejects.toThrow("NEXT_REDIRECT:/sign-in");
  });
});
