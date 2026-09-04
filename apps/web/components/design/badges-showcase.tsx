import { Badge, type BadgeProps } from "@/components/ui/badge";

const STATUS_BADGES: { variant: NonNullable<BadgeProps["variant"]>; label: string }[] = [
  { variant: "default", label: "NORMAL" },
  { variant: "info", label: "WATCHING" },
  { variant: "warning", label: "ANOMALY" },
  { variant: "gold", label: "HOT" },
  { variant: "positive", label: "ENTRY_CANDIDATE" },
  { variant: "negative", label: "BLOCKED_BY_RISK" },
];

/** The exact status vocabulary from docs/DESIGN.md §3. */
export function BadgesShowcase() {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {STATUS_BADGES.map(({ variant, label }) => (
        <Badge key={variant} variant={variant}>
          {label}
        </Badge>
      ))}
    </div>
  );
}
