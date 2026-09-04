import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function PlannedBadge({ milestone, className }: { milestone: string; className?: string }) {
  return (
    <Badge variant="planned" className={cn("shrink-0", className)}>
      Planejado ({milestone})
    </Badge>
  );
}
