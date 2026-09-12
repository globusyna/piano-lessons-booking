import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
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
import { usePianoStore } from "@/hooks/use-piano-store";
import {
  fmt,
  getOpenSlots,
  getStudentView,
  moveLesson,
  requestPause,
} from "@/lib/piano-data";

export const Route = createFileRoute("/s/$token")({
  head: () => ({
    meta: [
      { title: "Your piano lessons" },
      { name: "description", content: "See your next piano lesson, move a lesson or ask for a break." },
      { property: "og:title", content: "Your piano lessons" },
      { property: "og:description", content: "See your next piano lesson, move a lesson or ask for a break." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: StudentPage,
});

function StudentPage() {
  const { token } = Route.useParams();
  usePianoStore();
  const result = getStudentView(token);

  const [movingId, setMovingId] = useState<number | null>(null);
  const [movedId, setMovedId] = useState<number | null>(null);
  const [slotError, setSlotError] = useState<string | null>(null);
  const [pauseOpen, setPauseOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const slots = useMemo(
    () => (movingId ? getOpenSlots(movingId) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [movingId, result.ok ? JSON.stringify(result.data.lessons) : "", slotError],
  );

  if (!result.ok) {
    return (
      <Shell>
        <h1 className="text-3xl">This link isn't valid.</h1>
        <p className="mt-3 text-slate">Ask your teacher for a new one.</p>
      </Shell>
    );
  }

  const view = result.data;
  const finished = view.lessons.length === 0;

  const onPick = async (startsAt: string) => {
    if (!movingId) return;
    setBusy(true);
    const res = await moveLesson(movingId, startsAt);
    setBusy(false);
    if (res.ok) {
      setMovedId(movingId);
      setMovingId(null);
      setSlotError(null);
      toast("Lesson moved");
      setTimeout(() => setMovedId(null), 1400);
    } else {
      setSlotError(res.error.message);
    }
  };

  const onPause = async () => {
    setBusy(true);
    await requestPause(view.student.id);
    setBusy(false);
    setPauseOpen(false);
    toast("Break requested");
  };

  return (
    <Shell>
      <header>
        <p className="text-sm text-slate">Piano lessons</p>
        <h1 className="mt-1 text-2xl">{view.student.name}</h1>
      </header>

      {view.student.status === "paused" && (
        <Notice>
          Your lessons are paused. Your remaining {view.package.size - view.package.used} lessons stay on
          your account, and your teacher will be in touch to restart.
        </Notice>
      )}
      {view.student.status === "flagged" && (
        <Notice>
          There's something to sort out on your account. Your lessons are listed below and your teacher
          will be in touch.
        </Notice>
      )}

      {finished ? (
        <section className="mt-10">
          <h2 className="text-3xl leading-tight">
            That was lesson {view.package.size} of {view.package.size}.
          </h2>
          <p className="mt-3 text-slate">
            Your teacher will send an invoice and add the next set.
          </p>
        </section>
      ) : movingId ? (
        <MoveFlow
          slots={slots}
          error={slotError}
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
            <h2 className="text-sm font-bold tracking-wide text-slate uppercase">Upcoming lessons</h2>
            <ul className="mt-3 divide-y divide-border border-t border-b border-border">
              {view.lessons.map((l) => (
                <li
                  key={l.id}
                  className={`flex items-center justify-between py-3 ${
                    movedId === l.id ? "settle-in" : ""
                  }`}
                >
                  <div>
                    <p className="tnum">
                      {fmt.day(l.startsAt)} {fmt.dateShort(l.startsAt)} · {fmt.time(l.startsAt)}
                    </p>
                    <p className="tnum text-sm text-slate">
                      Lesson {l.seq} of {view.package.size}
                    </p>
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
              Your weekly time will be released and your teacher will be in touch. Your remaining
              lessons stay on your account.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep my lessons</AlertDialogCancel>
            <AlertDialogAction disabled={busy} onClick={(e) => { e.preventDefault(); void onPause(); }}>
              Ask for a break
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto w-full max-w-[420px] px-6 pt-12 pb-20">{children}</main>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return <p className="mt-6 border-l-2 border-felt pl-3 text-sm text-slate">{children}</p>;
}

function MoveFlow({
  slots,
  error,
  busy,
  onPick,
  onCancel,
}: {
  slots: string[];
  error: string | null;
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
        <button type="button" onClick={onCancel} className="text-sm text-slate underline underline-offset-4">
          Cancel
        </button>
      </div>

      {error && <p className="mt-4 border-l-2 border-felt pl-3 text-sm text-felt">{error}</p>}

      {slots.length === 0 ? (
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
