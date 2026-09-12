import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
import { pianoKeys } from "@/hooks/use-piano-store";
import { api, errorMessage } from "@/lib/api-client";
import { dateKey, fmt, weekStart } from "@/lib/piano-data";

export const Route = createFileRoute("/admin/")({
  component: WeekView,
});

function WeekView() {
  const [offset, setOffset] = useState(0);
  const [pendingRemove, setPendingRemove] = useState<{ id: number; name: string } | null>(null);
  const [approvingRequestId, setApprovingRequestId] = useState<number | null>(null);
  const queryClient = useQueryClient();
  const start = weekStart(offset);
  const startKey = dateKey(start);
  const week = useQuery({ queryKey: pianoKeys.week(startKey), queryFn: () => api.week(startKey) });

  const confirmRemove = async () => {
    if (!pendingRemove) return;
    try {
      await api.removeLesson(pendingRemove.id);
      await queryClient.invalidateQueries({ queryKey: pianoKeys.all });
      setPendingRemove(null);
      toast("Lesson removed");
    } catch (error) {
      toast.error(errorMessage(error));
    }
  };

  const approveMoveRequest = async (requestId: number) => {
    setApprovingRequestId(requestId);
    try {
      await api.approveMoveRequest(requestId);
      await queryClient.invalidateQueries({ queryKey: pianoKeys.all });
      toast("Move request approved");
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setApprovingRequestId(null);
    }
  };

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="text-2xl">Week of {fmt.date(start.toISOString())}</h1>
        <div className="flex items-center gap-4 text-sm">
          <button
            onClick={() => setOffset((o) => o - 1)}
            className="text-slate hover:text-foreground"
          >
            ← Previous
          </button>
          <button onClick={() => setOffset(0)} className="text-slate hover:text-foreground">
            This week
          </button>
          <button
            onClick={() => setOffset((o) => o + 1)}
            className="text-slate hover:text-foreground"
          >
            Next →
          </button>
        </div>
      </div>

      <div className="mt-6">
        {week.isPending ? (
          <p className="text-sm text-slate">Loading week…</p>
        ) : week.isError ? (
          <p className="text-sm text-felt">{errorMessage(week.error)}</p>
        ) : (
          <TimeGrid
            days={week.data}
            renderLesson={(cell, chip) => (
              <Popover>
                <PopoverTrigger className="h-full w-full cursor-pointer">{chip}</PopoverTrigger>
                <PopoverContent align="start" className="w-64">
                  <p className="text-base">{cell.studentName}</p>
                  <p className="tnum mt-1 text-sm text-slate">
                    {fmt.day(cell.startsAt)} {fmt.dateShort(cell.startsAt)} ·{" "}
                    {fmt.time(cell.startsAt)}
                  </p>
                  <p className="tnum text-sm text-slate">
                    Lesson {cell.seq} of {cell.size}
                  </p>
                  {cell.moveRequest && (
                    <div className="mt-4 border-l-2 border-felt pl-3">
                      <p className="text-sm font-medium">Move requested</p>
                      <p className="tnum mt-1 text-sm text-slate">
                        {fmt.day(cell.moveRequest.requestedStartsAt)}{" "}
                        {fmt.dateShort(cell.moveRequest.requestedStartsAt)} ·{" "}
                        {fmt.time(cell.moveRequest.requestedStartsAt)}
                      </p>
                      <button
                        type="button"
                        disabled={approvingRequestId === cell.moveRequest.id}
                        onClick={() => void approveMoveRequest(cell.moveRequest!.id)}
                        className="mt-3 bg-felt px-3 py-2 text-sm text-felt-foreground disabled:opacity-50"
                      >
                        Approve move request
                      </button>
                    </div>
                  )}
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
        )}
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
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                void confirmRemove();
              }}
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
