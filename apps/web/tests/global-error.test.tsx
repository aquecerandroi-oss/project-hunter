import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { loggerErrorMock } = vi.hoisted(() => ({ loggerErrorMock: vi.fn() }));
vi.mock("@/lib/logger", () => ({ logger: { error: loggerErrorMock, warn: vi.fn(), info: vi.fn(), debug: vi.fn() } }));

import GlobalError from "@/app/global-error";

afterEach(cleanup);

/**
 * `GlobalError` renders its own `<html>`/`<body>` (Next.js requirement for
 * this exact file) -- `render()` from Testing Library mounts into a
 * detached container, not `document.body` directly, so this only asserts
 * on the text/structure `GlobalError` itself produces, not that jsdom's
 * real `<html>` got replaced (that part is Next's own runtime contract,
 * not this component's to prove).
 */
describe("GlobalError: last-resort boundary, house style, no backstage (brief T3.28b)", () => {
  it("shows the one-sentence Portuguese copy and both actions, with no stack trace on screen", () => {
    const error = Object.assign(new Error("TypeError: x is not a function\n  at Foo (/app/bar.tsx:12:5)"), { digest: "abc123" });
    render(<GlobalError error={error} reset={vi.fn()} />);

    expect(screen.getByText("Algo deu errado.")).toBeInTheDocument();
    expect(screen.getByText("Não conseguimos carregar esta página agora.")).toBeInTheDocument();
    expect(screen.getByText("Tentar de novo")).toBeInTheDocument();
    expect(screen.getByText("Ir para o Dashboard")).toBeInTheDocument();
    // The raw error message/stack is never printed to the screen (D5/"sem backstage").
    expect(screen.queryByText(/is not a function/)).not.toBeInTheDocument();
    expect(screen.queryByText(/bar\.tsx/)).not.toBeInTheDocument();
  });

  it("shows the digest as a plain 'código de referência', never a file path or task id", () => {
    const error = Object.assign(new Error("boom"), { digest: "req_9f8e7d" });
    render(<GlobalError error={error} reset={vi.fn()} />);

    expect(screen.getByText(/código de referência: req_9f8e7d/)).toBeInTheDocument();
  });

  it("omits the digest line entirely when there is none", () => {
    render(<GlobalError error={new Error("boom")} reset={vi.fn()} />);

    expect(screen.queryByText(/código de referência/)).not.toBeInTheDocument();
  });

  it("calls reset() from 'Tentar de novo'", () => {
    const reset = vi.fn();
    render(<GlobalError error={new Error("boom")} reset={reset} />);

    screen.getByText("Tentar de novo").click();
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("logs the failure via the shared logger, never console directly", () => {
    const error = Object.assign(new Error("boom"), { digest: "abc123" });
    render(<GlobalError error={error} reset={vi.fn()} />);

    expect(loggerErrorMock).toHaveBeenCalledWith("global_render_failed", { error: "boom", digest: "abc123" });
  });
});
