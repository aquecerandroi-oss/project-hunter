"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { backoffDelayMs, MAX_AUTO_RETRIES } from "@/lib/retry-backoff";

export type MeUnavailableReason = "rate-limited" | "unavailable";

export interface MeUnavailableBannerProps {
  reason: MeUnavailableReason;
}

interface CountdownProps {
  delayMs: number;
  onElapsed: () => void;
}

/**
 * The ticking "Ns" half of the rate-limit message. Mounted with `key={attempt}`
 * by the caller below, so a fresh `attempt` gets a brand-new instance with its
 * own fresh `useState` lazy initializer -- the React-recommended way to
 * "reset state when an identity changes" without an effect
 * (react.dev/learn/you-might-not-need-an-effect#adjusting-some-state-when-a-prop-changes).
 * The only `setState` call inside the effect below runs from the interval's
 * own callback, never synchronously in the effect body, so this never trips
 * `react-hooks/set-state-in-effect`.
 */
function Countdown({ delayMs, onElapsed }: CountdownProps) {
  const [secondsLeft, setSecondsLeft] = useState(() => Math.ceil(delayMs / 1000));

  useEffect(() => {
    let remainingMs = delayMs;
    const tick = setInterval(() => {
      remainingMs = Math.max(0, remainingMs - 1000);
      setSecondsLeft(Math.ceil(remainingMs / 1000));
    }, 1000);
    const fire = setTimeout(onElapsed, delayMs);
    return () => {
      clearInterval(tick);
      clearTimeout(fire);
    };
  }, [delayMs, onElapsed]);

  return <>{secondsLeft}</>;
}

/**
 * Brief T3.28b: `[orgSlug]/layout.tsx`'s own `/me` fetch failing with
 * 429/5xx/network used to throw straight past `error.tsx` (a route-segment
 * boundary never catches its own directory's `layout.tsx` -- only the
 * segments nested below it) into Next's bare English "Application error"
 * screen, with the sidebar/topbar gone too. This renders in the layout's
 * `<main>` slot instead: the shell around it stays up (nav is still
 * usable), and `router.refresh()` re-runs the layout's server fetch on an
 * exponential backoff (`lib/retry-backoff.ts`), capped at
 * `MAX_AUTO_RETRIES` so a sustained outage never becomes an unbounded
 * request loop. The manual button stays live even after the cap so the
 * caller is never stuck waiting on nothing.
 */
export function MeUnavailableBanner({ reason }: MeUnavailableBannerProps) {
  const router = useRouter();
  const [attempt, setAttempt] = useState(0);

  const retrying = attempt < MAX_AUTO_RETRIES;

  function handleElapsed(): void {
    setAttempt((value) => value + 1);
    router.refresh();
  }

  function handleManualRetry(): void {
    setAttempt(0);
    router.refresh();
  }

  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-red/40 bg-bg-elevated p-10 text-center"
    >
      <p className="text-sm text-fg">
        {reason === "rate-limited" ? (
          retrying ? (
            <>
              O servidor limitou as requisições por um instante — tentando de novo em{" "}
              <Countdown key={attempt} delayMs={backoffDelayMs(attempt + 1)} onElapsed={handleElapsed} />s
            </>
          ) : (
            "O servidor limitou as requisições por um instante."
          )
        ) : (
          "Serviço indisponível."
        )}
      </p>
      <Button type="button" variant="outline" size="sm" onClick={handleManualRetry}>
        Tentar novamente
      </Button>
    </div>
  );
}
