import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { TimeGrid } from "@/components/TimeGrid";
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
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { usePianoStore } from "@/hooks/use-piano-store";
import { fmt, getWeek, removeLesson, weekStart } from "@/lib/piano-data";

export const Route = createFileRoute("/admin/")({
  component: WeekView,
});

function WeekView() {
  usePianoStore();
  const [offset, setOffset] = useState(0);
  const [pendingRemove, setPendingRemove] = useState<{ id: number; name: string } | null>(null);
  const days = getWeek(offset);
  const start = weekStart(offset);

  const confirmRemove = async () => {
    if (!pendingRemove) return;
    await removeLesson(pendingRemove.id);
    setPendingRemove(null);
    toast("Lesson removed");
  };

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="text-2xl">Week of {fmt.date(start.toISOString())}</h1>
        <div className="flex items-center gap-4 text-sm">
          <button onClick={() => setOffset((o) => o - 1)} className="text-slate hover:text-foreground">
            ← Previous
          </button>
          <button onClick={() => setOffset(0)} className="text-slate hover:text-foreground">
            This week
          </button>
          <button onClick={() => setOffset((o) => o + 1)} className="text-slate hover:text-foreground">
            Next →
          </button>
        </div>
      </div>

      <div className="mt-6">
        <TimeGrid
          days={days}
          renderLesson={(cell, chip) => (
            <Popover>
              <PopoverTrigger className="h-full w-full cursor-pointer">{chip}</PopoverTrigger>
              <PopoverContent align="start" className="w-64">
                <p className="text-base">{cell.studentName}</p>
                <p className="tnum mt-1 text-sm text-slate">
                  {fmt.day(cell.startsAt)} {fmt.dateShort(cell.startsAt)} · {fmt.time(cell.startsAt)}
                </p>
                <p className="tnum text-sm text-slate">
                  Lesson {cell.seq} of {cell.size}
                </p>
                <button
                  type="button"
                  onClick={() => setPendingRemove({ id: cell.lessonId, name: cell.studentName })}
                  className="mt-4 text-sm text-felt underline underline-offset-4"
                >
                  Remove
                </button>
              </PopoverContent>
            </Popover>
          )}
        />
      </div>

      <p className="mt-4 text-xs text-slate">
        Felt = booked lesson. Tinted = blackout. Empty = open.
      </p>

      <AlertDialog open={!!pendingRemove} onOpenChange={(o) => !o && setPendingRemove(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this lesson?</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingRemove?.name}'s lesson comes off the calendar and the time opens up again.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it</AlertDialogCancel>
            <AlertDialogAction onClick={(e) => { e.preventDefault(); void confirmRemove(); }}>
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
