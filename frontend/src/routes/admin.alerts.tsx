import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { PackageProgress } from "@/components/PackageProgress";
import { pianoKeys } from "@/hooks/use-piano-store";
import { api, errorMessage } from "@/lib/api-client";

export const Route = createFileRoute("/admin/alerts")({
  component: AlertsPage,
});

function AlertsPage() {
  const alerts = useQuery({ queryKey: pianoKeys.alerts(), queryFn: api.alerts });
  const queryClient = useQueryClient();

  if (alerts.isPending) return <p className="text-sm text-slate">Loading alerts…</p>;
  if (alerts.isError) return <p className="text-sm text-felt">{errorMessage(alerts.error)}</p>;
  const rows = alerts.data;

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl">Alerts</h1>
      <p className="mt-1 text-sm text-slate">Packages finished and waiting on an invoice.</p>

      {rows.length === 0 ? (
        <p className="mt-8 text-slate">Nothing to invoice.</p>
      ) : (
        <ul className="mt-6 divide-y divide-border border-t border-b border-border">
          {rows.map(({ student, package: pkg }) => (
            <li key={student.id} className="flex items-center justify-between gap-4 py-4">
              <div>
                <Link
                  to="/admin/students/$id"
                  params={{ id: String(student.id) }}
                  className="underline-offset-4 hover:underline"
                >
                  {student.name}
                </Link>
                <p className="tnum text-sm text-slate">Period {pkg.periodNo}</p>
              </div>
              <PackageProgress used={pkg.used} size={pkg.size} />
              <button
                onClick={async () => {
                  if (pkg.id === null) return;
                  try {
                    await api.markInvoiceSent(pkg.id);
                    await queryClient.invalidateQueries({ queryKey: pianoKeys.all });
                    toast("Invoice marked as sent");
                  } catch (error) {
                    toast.error(errorMessage(error));
                  }
                }}
                className="bg-felt px-3 py-2 text-sm text-felt-foreground"
              >
                Mark invoice sent
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
