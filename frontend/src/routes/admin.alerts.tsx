import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { PackageProgress } from "@/components/PackageProgress";
import { pianoKeys } from "@/hooks/use-piano-store";
import { api, errorMessage } from "@/lib/api-client";
import { fmt } from "@/lib/piano-data";

export const Route = createFileRoute("/admin/alerts")({
  component: AlertsPage,
});

// The price list, same as on student detail: a package's total is unconstrained
// but what can be bought in one go is still one of these.
const PACKAGE_SIZES = [5, 8, 10] as const;

/** The two things a finished package can have done to it, on the row that flagged it.
 *
 * Its own component so each row keeps its own chosen size, and so a package can
 * be topped up straight from the alert instead of going to student detail first.
 */
function InvoiceAlertActions({
  studentId,
  packageId,
  used,
  size,
}: {
  studentId: number;
  packageId: number | null;
  used: number;
  size: number;
}) {
  const queryClient = useQueryClient();
  const [renewSize, setRenewSize] = useState<number>(10);
  const refresh = () => queryClient.invalidateQueries({ queryKey: pianoKeys.all });

  return (
    <div className="flex flex-wrap items-center gap-2">
      <PackageProgress used={used} size={size} />
      <select
        value={renewSize}
        onChange={(e) => setRenewSize(Number(e.target.value))}
        aria-label="Lessons to add"
        className="tnum border border-input bg-transparent px-2 py-1.5 text-sm outline-none focus:border-felt"
      >
        {PACKAGE_SIZES.map((n) => (
          <option key={n} value={n}>
            {n} lessons
          </option>
        ))}
      </select>
      <button
        onClick={async () => {
          const total = size + renewSize;
          try {
            await api.renewPackage(studentId, renewSize);
            await refresh();
            toast(`Added ${renewSize} lessons — now ${total} total`);
          } catch (error) {
            toast.error(errorMessage(error));
          }
        }}
        className="border border-border px-3 py-2 text-sm hover:border-felt hover:text-felt"
      >
        Top up
      </button>
      <button
        disabled={packageId === null}
        onClick={async () => {
          if (packageId === null) return;
          try {
            await api.markInvoiceSent(packageId);
            await refresh();
            toast("Invoice marked as sent");
          } catch (error) {
            toast.error(errorMessage(error));
          }
        }}
        className="bg-felt px-3 py-2 text-sm text-felt-foreground disabled:opacity-40"
      >
        Mark invoice sent
      </button>
    </div>
  );
}

function AlertsPage() {
  const alerts = useQuery({ queryKey: pianoKeys.alerts(), queryFn: api.alerts });
  const queryClient = useQueryClient();

  if (alerts.isPending) return <p className="text-sm text-slate">Loading alerts…</p>;
  if (alerts.isError) return <p className="text-sm text-felt">{errorMessage(alerts.error)}</p>;
  const rows = alerts.data;

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl">Alerts</h1>
      <p className="mt-1 text-sm text-slate">Move requests and packages needing attention.</p>

      {rows.length === 0 ? (
        <p className="mt-8 text-slate">Nothing needs your attention.</p>
      ) : (
        <ul className="mt-6 divide-y divide-border border-t border-b border-border">
          {rows.map((alert) => (
            <li
              key={`${alert.type}-${alert.type === "invoice" ? alert.package.id : alert.moveRequest.id}`}
              className="flex flex-wrap items-center justify-between gap-4 py-4"
            >
              <div>
                <Link
                  to="/admin/students/$id"
                  params={{ id: String(alert.student.id) }}
                  className="underline-offset-4 hover:underline"
                >
                  {alert.student.name}
                </Link>
                {alert.type === "moveRequest" ? (
                  <>
                    <p className="mt-1 text-sm">Move request</p>
                    <p className="tnum text-sm text-slate">
                      {fmt.dayShort(alert.lesson.startsAt)} {fmt.dateShort(alert.lesson.startsAt)}{" "}
                      at {fmt.time(alert.lesson.startsAt)} →{" "}
                      {fmt.dayShort(alert.moveRequest.requestedStartsAt)}{" "}
                      {fmt.dateShort(alert.moveRequest.requestedStartsAt)} at{" "}
                      {fmt.time(alert.moveRequest.requestedStartsAt)}
                    </p>
                  </>
                ) : (
                  <p className="tnum text-sm text-slate">Period {alert.package.periodNo}</p>
                )}
              </div>
              {alert.type === "moveRequest" ? (
                <button
                  onClick={async () => {
                    try {
                      await api.approveMoveRequest(alert.moveRequest.id);
                      await queryClient.invalidateQueries({ queryKey: pianoKeys.all });
                      toast("Move request approved");
                    } catch (error) {
                      toast.error(errorMessage(error));
                    }
                  }}
                  className="bg-felt px-3 py-2 text-sm text-felt-foreground"
                >
                  Approve move request
                </button>
              ) : (
                <InvoiceAlertActions
                  studentId={alert.student.id}
                  packageId={alert.package.id}
                  used={alert.package.used}
                  size={alert.package.size}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
