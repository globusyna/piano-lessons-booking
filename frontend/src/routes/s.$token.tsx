import { createFileRoute } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
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
import { pianoKeys, useOpenSlots, useStudentView } from "@/hooks/use-piano-store";
import { api, ApiClientError, errorMessage } from "@/lib/api-client";
import { PAUSE_WEEKS, fmt, pauseReturnKey } from "@/lib/piano-data";

export const Route = createFileRoute("/s/$token")({
  head: () => ({
    meta: [
      { title: "Your piano lessons" },
      {
        name: "description",
        content: "See your next piano lesson, move a lesson or ask for a break.",
      },
      { property: "og:title", content: "Your piano lessons" },
      {
        property: "og:description",
        content: "See your next piano lesson, move a lesson or ask for a break.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: StudentPage,
});

function StudentPage() {
  const { token } = Route.useParams();
  const [movingId, setMovingId] = useState<number | null>(null);
  const [slotError, setSlotError] = useState<string | null>(null);
  const [pauseOpen, setPauseOpen] = useState(false);
  const [pauseWeeks, setPauseWeeks] = useState(1);
  const [busy, setBusy] = useState(false);
  const queryClient = useQueryClient();
  const viewQuery = useStudentView(token);
  const slotsQuery = useOpenSlots(token, movingId);

  if (viewQuery.isPending) {
    return (
      <Shell>
        <p className="text-sm text-slate">Loading your lessons…</p>
      </Shell>
    );
  }

  if (viewQuery.isError) {
    const invalid =
      viewQuery.error instanceof ApiClientError && viewQuery.error.code === "INVALID_TOKEN";
    return (
      <Shell>
        <h1 className="text-3xl">
          {invalid ? "This link isn't valid." : "Your lessons didn't load."}
        </h1>
        <p className="mt-3 text-slate">
          {invalid ? "Ask your teacher for a new one." : errorMessage(viewQuery.error)}
        </p>
      </Shell>
    );
  }

  const view = viewQuery.data;
  const finished = view.lessons.length === 0;

  const onPick = async (startsAt: string) => {
    if (!movingId) return;
    setBusy(true);
    try {
      await api.moveLesson(token, movingId, startsAt);
      setMovingId(null);
      setSlotError(null);
      await queryClient.invalidateQueries({ queryKey: pianoKeys.studentView(token) });
      toast("Sent request to Andrea");
    } catch (error) {
      setSlotError(errorMessage(error));
      await queryClient.invalidateQueries({ queryKey: pianoKeys.slots(token, movingId) });
    } finally {
      setBusy(false);
    }
  };

  const onPause = async () => {
    setBusy(true);
    try {
      await api.requestPause(token, pauseWeeks);
      await queryClient.invalidateQueries({ queryKey: pianoKeys.studentView(token) });
      setPauseOpen(false);
      toast(`Break booked until ${fmt.dateOnly(pauseReturnKey(pauseWeeks))}`);
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell>
      <header>
        <p className="text-sm text-slate">Piano lessons</p>
        <h1 className="mt-1 text-2xl">{view.student.name}</h1>
      </header>

      {view.student.status === "paused" && (
        <Notice>
          {view.pausedUntil ? (
            <>
              Paused until {fmt.dayOnly(view.pausedUntil)} {fmt.dateOnly(view.pausedUntil)}. Your
              remaining {view.package.size - view.package.used} lessons have moved on by the same
              number of weeks, so you keep every one of them.
            </>
          ) : (
            <>
              Your lessons are paused. Your remaining {view.package.size - view.package.used}{" "}
              lessons stay on your account, and your teacher will be in touch to restart.
            </>
          )}
        </Notice>
      )}
      {view.student.status === "flagged" && (
        <Notice>
          There's something to sort out on your account. Your lessons are listed below and your
          teacher will be in touch.
        </Notice>
      )}

      {finished ? (
        <section className="mt-10">
          <h2 className="text-3xl leading-tight">
            That was lesson {view.package.size} of {view.package.size}.
          </h2>
          <p className="mt-3 text-slate">Your teacher will send an invoice and add the next set.</p>
        </section>
      ) : movingId ? (
        <MoveFlow
          slots={slotsQuery.data ?? []}
          error={slotError ?? (slotsQuery.isError ? errorMessage(slotsQuery.error) : null)}
          loading={slotsQuery.isPending}
          busy={busy}
          onPick={onPick}
          onCancel={() => {
            setMovingId(null);
            setSlotError(null);
          }}
        />
      ) : (
        <>
          {view.nextLesson && (
            <section className="mt-10">
              <p className="text-sm text-slate">Next lesson</p>
              <p className="mt-2 text-xl">{fmt.day(view.nextLesson.startsAt)}</p>
              <p className="font-display tnum text-[4.5rem] leading-[1.05]">
                {fmt.time(view.nextLesson.startsAt)}
              </p>
              <p className="tnum mt-1 text-lg text-slate">
                {fmt.date(view.nextLesson.startsAt)} · lesson {view.nextLesson.seq} of{" "}
                {view.package.size}
              </p>
              {view.nextLesson.requestedStartsAt && (
                <Notice>
                  Sent request to Andrea for {fmt.day(view.nextLesson.requestedStartsAt)}{" "}
                  {fmt.dateShort(view.nextLesson.requestedStartsAt)} at{" "}
                  {fmt.time(view.nextLesson.requestedStartsAt)}.
                </Notice>
              )}
              {view.nextLesson.canMove && (
                <button
                  type="button"
                  onClick={() => setMovingId(view.nextLesson!.id)}
                  className="mt-5 inline-flex items-center bg-felt px-4 py-2.5 text-felt-foreground"
                >
                  Move lesson
                </button>
              )}
            </section>
          )}

          <section className="mt-12">
            <h2 className="text-sm font-bold tracking-wide text-slate uppercase">
              Upcoming lessons
            </h2>
            <ul className="mt-3 divide-y divide-border border-t border-b border-border">
              {view.lessons.map((l) => (
                <li key={l.id} className="flex items-center justify-between gap-4 py-3">
                  <div>
                    <p className="tnum">
                      {fmt.day(l.startsAt)} {fmt.dateShort(l.startsAt)} · {fmt.time(l.startsAt)}
                    </p>
                    <p className="tnum text-sm text-slate">
                      Lesson {l.seq} of {view.package.size}
                    </p>
                    {l.requestedStartsAt && (
                      <p className="mt-1 text-sm text-felt">
                        Move requested for {fmt.dayShort(l.requestedStartsAt)}{" "}
                        {fmt.dateShort(l.requestedStartsAt)} at {fmt.time(l.requestedStartsAt)}
                      </p>
                    )}
                  </div>
                  {l.canMove && (
                    <button
                      type="button"
                      onClick={() => setMovingId(l.id)}
                      className="text-sm text-felt underline underline-offset-4"
                    >
                      Move
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </section>

          {view.canRequestPause && (
            <div className="mt-14 mb-16">
              <button
                type="button"
                onClick={() => setPauseOpen(true)}
                className="text-sm text-slate underline underline-offset-4"
              >
                Ask for a break
              </button>
            </div>
          )}
        </>
      )}

      <AlertDialog open={pauseOpen} onOpenChange={setPauseOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Ask for a break</AlertDialogTitle>
            <AlertDialogDescription>
              Choose how long. Your weekly time goes back on the calendar for those weeks, and every
              lesson you have left moves on by the same number of weeks — you keep all of them.
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
              Your first lesson back is on or after {fmt.dayOnly(pauseReturnKey(pauseWeeks))}{" "}
              {fmt.dateOnly(pauseReturnKey(pauseWeeks))}.
            </p>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep my lessons</AlertDialogCancel>
            <AlertDialogAction
              disabled={busy}
              onClick={(e) => {
                e.preventDefault();
                void onPause();
              }}
            >
              Ask for a break
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <main className="mx-auto w-full max-w-[420px] px-6 pt-12 pb-20">{children}</main>;
}

function Notice({ children }: { children: React.ReactNode }) {
  return <p className="mt-6 border-l-2 border-felt pl-3 text-sm text-slate">{children}</p>;
}

function MoveFlow({
  slots,
  error,
  loading,
  busy,
  onPick,
  onCancel,
}: {
  slots: string[];
  error: string | null;
  loading: boolean;
  busy: boolean;
  onPick: (s: string) => void;
  onCancel: () => void;
}) {
  const groups = slots.reduce<Record<string, string[]>>((acc, s) => {
    const key = s.slice(0, 10);
    (acc[key] ??= []).push(s);
    return acc;
  }, {});

  return (
    <section className="mt-10">
      <div className="flex items-baseline justify-between">
        <h2 className="text-2xl">Pick a new time</h2>
        <button
          type="button"
          onClick={onCancel}
          className="text-sm text-slate underline underline-offset-4"
        >
          Cancel
        </button>
      </div>

      {error && <p className="mt-4 border-l-2 border-felt pl-3 text-sm text-felt">{error}</p>}

      {loading ? (
        <p className="mt-6 text-slate">Loading open times…</p>
      ) : slots.length === 0 ? (
        <p className="mt-6 text-slate">
          No open times in the next three weeks. Message your teacher to find something.
        </p>
      ) : (
        <div className="mt-6 space-y-6">
          {Object.entries(groups).map(([, list]) => (
            <div key={list[0]}>
              <p className="text-sm text-slate">
                {fmt.day(list[0]!)} {fmt.dateShort(list[0]!)}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {list.map((s) => (
                  <button
                    key={s}
                    type="button"
                    disabled={busy}
                    onClick={() => onPick(s)}
                    className="tnum border border-border px-3 py-2 text-sm hover:border-felt hover:text-felt disabled:opacity-50"
                  >
                    {fmt.time(s)}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
