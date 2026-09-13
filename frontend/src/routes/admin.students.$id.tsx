import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
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
import { pianoKeys, useStudent } from "@/hooks/use-piano-store";
import { api, errorMessage, type PackagePreview } from "@/lib/api-client";
import { PAUSE_WEEKS, ROW_TIMES, fmt, pauseReturnKey } from "@/lib/piano-data";

export const Route = createFileRoute("/admin/students/$id")({
  component: StudentDetail,
});

// The price list. What a package can grow to is unconstrained -- topping a 10
// up by 10 makes a 20 -- but what can be bought in one go is still one of these.
const PACKAGE_SIZES = [5, 8, 10] as const;

const DAYS = [
  [1, "Monday"],
  [2, "Tuesday"],
  [3, "Wednesday"],
  [4, "Thursday"],
  [5, "Friday"],
] as const;

/** The dates a confirm would create, or the reason there are none to show. */
function PlannedDates({ preview }: { preview: UseQueryResult<PackagePreview> }) {
  if (preview.isError)
    return <p className="mt-4 text-sm text-felt">{errorMessage(preview.error)}</p>;
  if (!preview.data) return <p className="mt-4 text-sm text-slate">Working out the dates…</p>;
  return (
    <ol className="mt-4 max-h-56 overflow-y-auto border border-border">
      {preview.data.dates.map((date, index) => (
        <li
          key={date}
          className="flex items-baseline gap-3 border-b border-border px-3 py-1.5 text-sm last:border-b-0"
        >
          <span className="tnum w-5 text-slate">{index + 1}</span>
          <span className="flex-1">
            {fmt.dayShort(date)} {fmt.date(date)}
          </span>
          <span className="tnum text-slate">{fmt.time(date)}</span>
        </li>
      ))}
    </ol>
  );
}

function StudentDetail() {
  const { id } = Route.useParams();
  const studentId = Number(id);
  const detail = useStudent(studentId);
  const queryClient = useQueryClient();
  const [packageSize, setPackageSize] = useState(10);
  const [confirmPackage, setConfirmPackage] = useState(false);
  const [renewSize, setRenewSize] = useState(10);
  const [confirmRenew, setConfirmRenew] = useState(false);
  const [confirmPause, setConfirmPause] = useState(false);
  const [pauseWeeks, setPauseWeeks] = useState(1);

  // What the two confirm dialogs show. Asked for only while a dialog is open,
  // and answered by the endpoint that runs the real placement and writes
  // nothing -- so the dates below are the dates confirming creates, blackout
  // skips included, and a slot that cannot be placed says so here rather than
  // after the fact.
  const packagePreview = useQuery({
    queryKey: [...pianoKeys.student(studentId), "package-preview", packageSize],
    queryFn: () => api.packagePreview(studentId, packageSize),
    enabled: confirmPackage,
    retry: false,
  });
  const renewPreview = useQuery({
    queryKey: [...pianoKeys.student(studentId), "renew-preview", renewSize],
    queryFn: () => api.renewalPreview(studentId, renewSize),
    enabled: confirmRenew,
    retry: false,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: pianoKeys.all });

  if (detail.isPending) return <p className="text-sm text-slate">Loading student…</p>;
  if (detail.isError) return <p className="text-sm text-felt">{errorMessage(detail.error)}</p>;
  const student = detail.data.student;

  if (!student) {
    return (
      <div>
        <h1 className="text-2xl">No such student.</h1>
        <Link
          to="/admin/students"
          className="mt-3 inline-block text-sm text-felt underline underline-offset-4"
        >
          Back to students
        </Link>
      </div>
    );
  }

  const history = detail.data.lessons;

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

        <h2 className="mt-10 text-sm font-bold uppercase tracking-wide text-slate">
          Lesson history
        </h2>
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
              onChange={async (e) => {
                try {
                  await api.setWeeklySlot(student.id, Number(e.target.value), student.slotTime);
                  await refresh();
                } catch (error) {
                  toast.error(errorMessage(error));
                }
              }}
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
              onChange={async (e) => {
                try {
                  await api.setWeeklySlot(student.id, student.slotDay, e.target.value);
                  await refresh();
                } catch (error) {
                  toast.error(errorMessage(error));
                }
              }}
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
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate">Break</h2>
          {student.status === "paused" ? (
            <div className="mt-3">
              <p className="text-sm">
                {student.pausedUntil
                  ? `Paused until ${fmt.dayOnly(student.pausedUntil)} ${fmt.dateOnly(
                      student.pausedUntil,
                    )}`
                  : "Paused"}
              </p>
              <button
                onClick={async () => {
                  try {
                    await api.resumeStudent(student.id);
                    await refresh();
                    toast("Break ended");
                  } catch (error) {
                    toast.error(errorMessage(error));
                  }
                }}
                className="mt-2 bg-felt px-3 py-2 text-sm text-felt-foreground"
              >
                Resume now
              </button>
              <p className="mt-2 text-sm text-slate">
                Lessons stay where the break moved them. The original times are not taken back.
              </p>
            </div>
          ) : (
            <div className="mt-3">
              <button
                disabled={student.status === "flagged"}
                onClick={() => setConfirmPause(true)}
                className="bg-felt px-3 py-2 text-sm text-felt-foreground disabled:opacity-40"
              >
                Pause
              </button>
              <p className="mt-2 text-sm text-slate">
                {student.status === "flagged"
                  ? "Clear the flag before starting a break."
                  : "Frees the weekly slot and moves the remaining lessons out by the same weeks."}
              </p>
            </div>
          )}
        </section>

        <section>
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate">Flag</h2>
          <button
            onClick={async () => {
              const next = student.status === "flagged" ? "active" : "flagged";
              try {
                await api.setStudentStatus(student.id, next);
                await refresh();
                toast(next === "flagged" ? "Account flagged" : "Flag cleared");
              } catch (error) {
                toast.error(errorMessage(error));
              }
            }}
            className="mt-3 border border-border px-3 py-2 text-sm hover:border-felt hover:text-felt"
          >
            {student.status === "flagged" ? "Clear flag" : "Flag account"}
          </button>
          <p className="mt-2 text-sm text-slate">
            {student.status === "paused"
              ? "Flagging a paused student ends the break on the record."
              : "For an open question on the account. Stops moves and breaks."}
          </p>
        </section>

        <section>
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate">Invoice</h2>
          <p className="mt-2 text-sm text-slate">
            {student.pkg.used < student.pkg.size
              ? "Available when the package is finished."
              : "Ready to mark as sent."}
          </p>
          <button
            disabled={student.pkg.used < student.pkg.size || student.pkg.id === null}
            onClick={async () => {
              if (student.pkg.id === null) return;
              try {
                await api.markInvoiceSent(student.pkg.id);
                await refresh();
                toast("Invoice marked as sent");
              } catch (error) {
                toast.error(errorMessage(error));
              }
            }}
            className="mt-2 bg-felt px-3 py-2 text-sm text-felt-foreground disabled:opacity-40"
          >
            Mark invoice sent
          </button>
        </section>

        <section>
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate">Renew package</h2>
          <p className="mt-2 text-sm text-slate">
            Adds to the package already running. Everything booked keeps its date and the new
            lessons carry on from the last of them.
          </p>
          <div className="mt-3 flex gap-2">
            <select
              value={renewSize}
              onChange={(e) => setRenewSize(Number(e.target.value))}
              className="tnum border border-input bg-transparent px-2 py-1.5 text-sm outline-none focus:border-felt"
            >
              {PACKAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n} lessons
                </option>
              ))}
            </select>
            <button
              onClick={() => setConfirmRenew(true)}
              className="border border-border px-3 py-2 text-sm hover:border-felt hover:text-felt"
            >
              Top up
            </button>
          </div>
        </section>

        <section>
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate">New package</h2>
          <div className="mt-3 flex gap-2">
            <select
              value={packageSize}
              onChange={(e) => setPackageSize(Number(e.target.value))}
              className="tnum border border-input bg-transparent px-2 py-1.5 text-sm outline-none focus:border-felt"
            >
              {PACKAGE_SIZES.map((n) => (
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

      <AlertDialog open={confirmPause} onOpenChange={setConfirmPause}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Pause {student.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              The weekly slot is free for these weeks and every remaining lesson moves out by the
              same number of weeks. Nothing is lost from the package.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div>
            <div className="flex flex-wrap gap-2">
              {PAUSE_WEEKS.map((weeks) => (
                <button
                  key={weeks}
                  type="button"
                  onClick={() => setPauseWeeks(weeks)}
                  aria-pressed={pauseWeeks === weeks}
                  className={
                    pauseWeeks === weeks
                      ? "tnum border border-felt px-3 py-2 text-sm text-felt"
                      : "tnum border border-border px-3 py-2 text-sm hover:border-felt hover:text-felt"
                  }
                >
                  {weeks} {weeks === 1 ? "week" : "weeks"}
                </button>
              ))}
            </div>
            <p className="mt-3 text-sm text-slate">
              Back on {fmt.dayOnly(pauseReturnKey(pauseWeeks))}{" "}
              {fmt.dateOnly(pauseReturnKey(pauseWeeks))}.
            </p>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={async (e) => {
                e.preventDefault();
                try {
                  await api.pauseStudent(student.id, pauseWeeks);
                  await refresh();
                  setConfirmPause(false);
                  toast(`Paused until ${fmt.dateOnly(pauseReturnKey(pauseWeeks))}`);
                } catch (error) {
                  toast.error(errorMessage(error));
                }
              }}
            >
              Pause
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmRenew} onOpenChange={setConfirmRenew}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Top up this package?</AlertDialogTitle>
            <AlertDialogDescription>
              {renewPreview.isError ? (
                <>
                  These {renewSize} lessons cannot go on {student.name}'s weekly slot.
                </>
              ) : (
                <>
                  {renewSize} more lessons, carrying on from the last one already booked. The
                  package becomes {student.pkg.size + renewSize} lessons in total, nothing already
                  scheduled moves, and nothing is created until you confirm.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <PlannedDates preview={renewPreview} />
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={!renewPreview.data}
              onClick={async (e) => {
                e.preventDefault();
                // Read the total before the refetch replaces it.
                const total = student.pkg.size + renewSize;
                try {
                  await api.renewPackage(student.id, renewSize);
                  await refresh();
                  setConfirmRenew(false);
                  toast(`Added ${renewSize} lessons — now ${total} total`);
                } catch (error) {
                  toast.error(errorMessage(error));
                }
              }}
            >
              Top up
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmPackage} onOpenChange={setConfirmPackage}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Open a new package?</AlertDialogTitle>
            <AlertDialogDescription>
              {packagePreview.isError ? (
                <>
                  These {packageSize} lessons cannot go on {student.name}'s weekly slot.
                </>
              ) : (
                <>
                  The dates {student.name} gets, rolled past anything blacked out or already taken.
                  Nothing is created until you confirm.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <PlannedDates preview={packagePreview} />
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={!packagePreview.data}
              onClick={async (e) => {
                e.preventDefault();
                try {
                  await api.openPackage(student.id, packageSize);
                  await refresh();
                  setConfirmPackage(false);
                  toast("Package opened");
                } catch (error) {
                  toast.error(errorMessage(error));
                }
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
