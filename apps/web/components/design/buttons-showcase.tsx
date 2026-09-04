import { Button, type ButtonProps } from "@/components/ui/button";

const VARIANTS: { variant: NonNullable<ButtonProps["variant"]>; label: string }[] = [
  { variant: "default", label: "Primário" },
  { variant: "secondary", label: "Secundário" },
  { variant: "outline", label: "Outline" },
  { variant: "ghost", label: "Ghost" },
  { variant: "destructive", label: "Destrutivo" },
];

/** docs/DESIGN.md §3: gold primary is rare -- one per screen -- secondary is bordered, destructive is red. */
export function ButtonsShowcase() {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {VARIANTS.map(({ variant, label }) => (
        <Button key={variant} variant={variant}>
          {label}
        </Button>
      ))}
    </div>
  );
}
