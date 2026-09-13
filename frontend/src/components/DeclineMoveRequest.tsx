import { useState } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
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
import { pianoKeys } from "@/hooks/use-piano-store";
import { api, errorMessage } from "@/lib/api-client";

/** Decline a move request, with a reason the student will read.
 *
 * Shared by the alerts list and the week-view popover so the two cannot drift
 * apart on what a decline says or asks for. The reason is genuinely optional --
 * confirming with the field empty sends no reason at all, and the student is
 * then told the move was refused without one.
 */
export function DeclineMoveRequest({
  requestId,
  studentName,
  className = "border border-border px-3 py-2 text-sm hover:border-felt hover:text-felt",
}: {
  requestId: number;
  studentName: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const queryClient = useQueryClient();

  const confirm = async () => {
    setBusy(true);
    try {
      await api.declineMoveRequest(requestId, reason.trim() || undefined);
      await queryClient.invalidateQueries({ queryKey: pianoKeys.all });
      setOpen(false);
      setReason("");
      toast("Move request declined.");
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button type="button" disabled={busy} onClick={() => setOpen(true)} className={className}>
        Decline
      </button>
      <AlertDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setReason("");
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Decline this move request?</AlertDialogTitle>
            <AlertDialogDescription>
              {studentName}'s lesson stays where it is, and the time they asked for opens up again.
              They'll see that you declined, and can ask for a different time.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <label className="block text-sm">
            <span className="text-slate">Reason (optional)</span>
            <input
              type="text"
              value={reason}
              maxLength={500}
              onChange={(e) => setReason(e.target.value)}
              placeholder="I teach a masterclass that afternoon"
              className="mt-1 w-full border border-input bg-transparent px-2 py-1.5 text-sm outline-none focus:border-felt"
            />
          </label>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it</AlertDialogCancel>
            <AlertDialogAction
              disabled={busy}
              onClick={(e) => {
                e.preventDefault();
                void confirm();
              }}
            >
              Decline
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
