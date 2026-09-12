import { createFileRoute, Link } from "@tanstack/react-router";
import { toast } from "sonner";
import { PackageProgress } from "@/components/PackageProgress";
import { usePianoStore } from "@/hooks/use-piano-store";
import { alerts, markInvoiceSent } from "@/lib/piano-data";

export const Route = createFileRoute("/admin/alerts")({
  component: AlertsPage,
});

function AlertsPage() {
  usePianoStore();
  const rows = alerts();

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl">Alerts</h1>
      <p className="mt-1 text-sm text-slate">Packages finished and waiting on an invoice.</p>

      {rows.length === 0 ? (
        <p className="mt-8 text-slate">Nothing to invoice.</p>
      ) : (
        <ul className="mt-6 divide-y divide-border border-t border-b border-border">
          {rows.map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-4 py-4">
              <div>
                <Link
                  to="/admin/students/$id"
                  params={{ id: String(s.id) }}
                  className="underline-offset-4 hover:underline"
                >
                  {s.name}
                </Link>
                <p className="tnum text-sm text-slate">Period {s.pkg.periodNo}</p>
              </div>
              <PackageProgress used={s.pkg.used} size={s.pkg.size} />
              <button
                onClick={async () => {
                  await markInvoiceSent(s.id);
                  toast("Invoice marked as sent");
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
