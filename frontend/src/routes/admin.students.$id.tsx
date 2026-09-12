import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { CopyLinkButton } from "@/components/CopyLinkButton";
import { PackageProgress } from "@/components/PackageProgress";
import { StatusPill } from "@/components/StatusPill";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { usePianoStore } from "@/hooks/use-piano-store";
import {
  ROW_TIMES,
  fmt,
  lessonHistory,
  markInvoiceSent,
  openPackage,
  setStudentStatus,
  setWeeklySlot,
} from "@/lib/piano-data";

export const Route = createFileRoute("/admin/students/$id")({
  component: StudentDetail,
});

const DAYS = [
  [1, "Monday"],
  [2, "Tuesday"],
  [3, "Wednesday"],
  [4, "Thursday"],
  [5, "Friday"],
] as const;

function StudentDetail() {
  const { id } = Route.useParams();
  const state = usePianoStore();
  const student = state.students.find((s) => s.id === Number(id));
  const [packageSize, setPackageSize] = useState(10);
  const [confirmPackage, setConfirmPackage] = useState(false);

  if (!student) {
    return (
      <div>
        <h1 className="text-2xl">No such student.</h1>
        <Link to="/admin/students" className="mt-3 inline-block text-sm text-felt underline underline-offset-4">
          Back to students
        </Link>
      </div>
    );
  }

  const history = lessonHistory(student.id);

  return (
    <div className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div>
        <Link to="/admin/students" className="text-sm text-slate underline underline-offset-4">
          ← Students
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="text-3xl">{student.name}</h1>
          <StatusPill status={student.status} />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-4">
          <CopyLinkButton token={student.token} />
          <span className="tnum text-sm text-slate">Period {student.pkg.periodNo}</span>
          <PackageProgress used={student.pkg.used} size={student.pkg.size} />
        </div>

        <h2 className="mt-10 text-sm font-bold uppercase tracking-wide text-slate">Lesson history</h2>
        <ul className="mt-3 divide-y divide-border border-t border-b border-border">
          {history.map((l) => (
            <li key={l.id} className="flex items-center justify-between py-2.5">
              <span className="tnum text-sm">
                {fmt.day(l.startsAt)} {fmt.dateShort(l.startsAt)} · {fmt.time(l.startsAt)}
              </span>
              <span className="tnum text-sm text-slate">
                Lesson {l.seq} · {l.status === "done" ? "Done" : "Scheduled"}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <aside className="space-y-8">
        <section>
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate">Weekly slot</h2>
          <div className="mt-3 flex gap-2">
            <select
              value={student.slotDay}
              onChange={(e) => setWeeklySlot(student.id, Number(e.target.value), student.slotTime)}
              className="border border-input bg-transparent px-2 py-1.5 text-sm outline-none focus:border-felt"
            >
              {DAYS.map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
            <select
              value={student.slotTime}
              onChange={(e) => setWeeklySlot(student.id, student.slotDay, e.target.value)}
              className="tnum border border-input bg-transparent px-2 py-1.5 text-sm outline-none focus:border-felt"
            >
              {ROW_TIMES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
        </section>

        <section>
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate">Status</h2>
          <div className="mt-3 flex gap-4 text-sm">
            {(["active", "paused", "flagged"] as const).map((s) => (
              <button
                key={s}
                onClick={async () => {
                  await setStudentStatus(student.id, s);
                  toast(`Status set to ${s}`);
                }}
                className={student.status === s ? "text-felt" : "text-slate hover:text-foreground"}
              >
                {s[0]!.toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate">Invoice</h2>
          <p className="mt-2 text-sm text-slate">
            {student.invoiceSent ? "Invoice marked as sent." : "Not marked as sent."}
          </p>
          <button
            disabled={student.invoiceSent}
            onClick={async () => {
              await markInvoiceSent(student.id);
              toast("Invoice marked as sent");
            }}
            className="mt-2 bg-felt px-3 py-2 text-sm text-felt-foreground disabled:opacity-40"
          >
            Mark invoice sent
          </button>
        </section>

        <section>
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate">New package</h2>
          <div className="mt-3 flex gap-2">
            <select
              value={packageSize}
              onChange={(e) => setPackageSize(Number(e.target.value))}
              className="tnum border border-input bg-transparent px-2 py-1.5 text-sm outline-none focus:border-felt"
            >
              {[5, 8, 10].map((n) => (
                <option key={n} value={n}>
                  {n} lessons
                </option>
              ))}
            </select>
            <button
              onClick={() => setConfirmPackage(true)}
              className="bg-felt px-3 py-2 text-sm text-felt-foreground"
            >
              Open package
            </button>
          </div>
        </section>
      </aside>

      <AlertDialog open={confirmPackage} onOpenChange={setConfirmPackage}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Open a new package?</AlertDialogTitle>
            <AlertDialogDescription>
              {packageSize} lessons are placed on {student.name}'s weekly slot, starting next week.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={async (e) => {
                e.preventDefault();
                await openPackage(student.id, packageSize);
                setConfirmPackage(false);
                toast("Package opened");
              }}
            >
              Open package
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
