import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { CopyLinkButton } from "@/components/CopyLinkButton";
import { PackageProgress } from "@/components/PackageProgress";
import { StatusPill } from "@/components/StatusPill";
import { useStudents } from "@/hooks/use-piano-store";
import { errorMessage } from "@/lib/api-client";
import type { StudentStatus } from "@/lib/piano-data";

export const Route = createFileRoute("/admin/students/")({
  component: StudentsPage,
});

const DAY_NAMES = ["", "Mon", "Tue", "Wed", "Thu", "Fri"];
const FILTERS: Array<"all" | StudentStatus> = ["all", "active", "paused", "flagged"];

function StudentsPage() {
  const students = useStudents();
  const [filter, setFilter] = useState<"all" | StudentStatus>("all");

  if (students.isPending) return <p className="text-sm text-slate">Loading students…</p>;
  if (students.isError) return <p className="text-sm text-felt">{errorMessage(students.error)}</p>;
  const rows = students.data.filter((s) => filter === "all" || s.status === filter);

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="text-2xl">Students</h1>
        <div className="flex gap-4 text-sm">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={filter === f ? "text-felt" : "text-slate hover:text-foreground"}
            >
              {f === "all" ? "All" : f[0]!.toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <table className="mt-6 w-full border-t border-border text-left">
        <thead>
          <tr className="text-xs uppercase tracking-wide text-slate">
            <th className="border-b border-border py-2 font-normal">Name</th>
            <th className="border-b border-border py-2 font-normal">Status</th>
            <th className="border-b border-border py-2 font-normal">Weekly slot</th>
            <th className="border-b border-border py-2 font-normal">Package</th>
            <th className="border-b border-border py-2 font-normal">Link</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.id}>
              <td className="border-b border-border py-3">
                <Link
                  to="/admin/students/$id"
                  params={{ id: String(s.id) }}
                  className="underline-offset-4 hover:underline"
                >
                  {s.name}
                </Link>
              </td>
              <td className="border-b border-border py-3">
                <StatusPill status={s.status} />
              </td>
              <td className="tnum border-b border-border py-3 text-sm text-slate">
                {DAY_NAMES[s.slotDay]} {s.slotTime}
              </td>
              <td className="border-b border-border py-3">
                <PackageProgress used={s.pkg.used} size={s.pkg.size} />
              </td>
              <td className="border-b border-border py-3">
                <CopyLinkButton token={s.token} />
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={5} className="py-6 text-sm text-slate">
                No students with that status.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
