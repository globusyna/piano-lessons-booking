import type { StudentStatus } from "@/lib/piano-data";
import { cn } from "@/lib/utils";

const label: Record<StudentStatus, string> = {
  active: "Active",
  paused: "Paused",
  flagged: "Flagged",
};

export function StatusPill({ status, className }: { status: StudentStatus; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center border px-2 py-0.5 text-xs uppercase tracking-wide",
        status === "active" && "border-border text-foreground",
        status === "paused" && "border-border text-muted-foreground",
        status === "flagged" && "border-felt text-felt",
        className,
      )}
    >
      {label[status]}
    </span>
  );
}
