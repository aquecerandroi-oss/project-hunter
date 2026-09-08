import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { refreshMock } = vi.hoisted(() => ({ refreshMock: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: refreshMock }) }));

import { MeUnavailableBanner } from "@/components/layout/me-unavailable-banner";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  refreshMock.mockClear();
});

describe("MeUnavailableBanner: a 429 from `/me` gets an honest, counting-down retry (brief T3.28b)", () => {
  it("shows the rate-limit copy with a live countdown", () => {
    vi.useFakeTimers();
    render(<MeUnavailableBanner reason="rate-limited" />);

    expect(screen.getByText(/O servidor limitou as requisições por um instante — tentando de novo em 2s/)).toBeInTheDocument();
  });

  it("shows the generic 'Serviço indisponível' copy for a 5xx/network failure, with no countdown", () => {
    vi.useFakeTimers();
    render(<MeUnavailableBanner reason="unavailable" />);

    expect(screen.getByText("Serviço indisponível.")).toBeInTheDocument();
    expect(screen.queryByText(/tentando de novo/)).not.toBeInTheDocument();
  });

  it("calls router.refresh() automatically after the backoff delay elapses", () => {
    vi.useFakeTimers();
    render(<MeUnavailableBanner reason="rate-limited" />);

    expect(refreshMock).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(refreshMock).toHaveBeenCalledTimes(1);
  });

  it("stops auto-retrying after MAX_AUTO_RETRIES (3), keeping the manual button available", () => {
    vi.useFakeTimers();
    render(<MeUnavailableBanner reason="rate-limited" />);

    act(() => {
      vi.advanceTimersByTime(2000); // 1st retry (2s)
    });
    act(() => {
      vi.advanceTimersByTime(4000); // 2nd retry (4s)
    });
    act(() => {
      vi.advanceTimersByTime(8000); // 3rd retry (8s)
    });
    expect(refreshMock).toHaveBeenCalledTimes(3);

    // A 4th retry never fires on its own -- no further delay is scheduled.
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(refreshMock).toHaveBeenCalledTimes(3);
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });

  it("the manual 'Tentar novamente' button refreshes immediately and resets the auto-retry counter", () => {
    vi.useFakeTimers();
    render(<MeUnavailableBanner reason="rate-limited" />);

    act(() => {
      screen.getByRole("button", { name: "Tentar novamente" }).click();
    });
    expect(refreshMock).toHaveBeenCalledTimes(1);
  });
});
