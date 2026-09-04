import { Check } from "lucide-react";

import { STEP_LABELS } from "@/components/onboarding/labels";
import { STEP_COUNT, type WizardStep } from "@/components/onboarding/wizard-state";
import { cn } from "@/lib/utils";

export interface OnboardingProgressProps {
  step: WizardStep;
}

/** Keyboard-accessible step indicator: an ordered list, current step marked with `aria-current`. */
export function OnboardingProgress({ step }: OnboardingProgressProps) {
  const steps = Array.from({ length: STEP_COUNT }, (_, i) => (i + 1) as WizardStep);

  return (
    <ol className="flex flex-wrap items-center gap-2 text-xs" aria-label="Progresso do onboarding">
      {steps.map((s) => {
        const done = s < step;
        const current = s === step;
        return (
          <li key={s} aria-current={current ? "step" : undefined} className="flex items-center gap-2">
            <span
              className={cn(
                "flex size-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-medium",
                done && "border-accent bg-accent text-accent-foreground",
                current && !done && "border-accent text-accent",
                !current && !done && "border-border text-muted",
              )}
            >
              {done ? <Check className="size-3.5" /> : s}
            </span>
            <span className={cn("hidden sm:inline", current ? "font-medium text-foreground" : "text-muted")}>
              {STEP_LABELS[s]}
            </span>
            {s !== STEP_COUNT && <span className="mx-1 h-px w-4 bg-border sm:mx-2 sm:w-6" aria-hidden="true" />}
          </li>
        );
      })}
    </ol>
  );
}
