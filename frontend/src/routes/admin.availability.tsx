import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { usePianoStore } from "@/hooks/use-piano-store";
import {
  ROW_TIMES,
  addBlackout,
  fmt,
  removeBlackout,
  setHours,
} from "@/lib/piano-data";

export const Route = createFileRoute("/admin/availability")({
  component: AvailabilityPage,
});

const DAYS = [
  [1, "Monday"],
  [2, "Tuesday"],
  [3, "Wednesday"],
  [4, "Thursday"],
  [5, "Friday"],
] as const;

function AvailabilityPage() {
  const state = usePianoStore();
  const [date, setDate] = useState("");
  const [time, setTime] = useState(ROW_TIMES[0]!);
  const [note, setNote] = useState("");

  const toggle = async (day: number, t: string) => {
    const current = state.hours[day] ?? [];
    const next = current.includes(t) ? current.filter((x) => x !== t) : [...current, t].sort();
    await setHours(day, next);
  };

  const add = async () => {
    if (!date) return;
    const d = new Date(`${date}T${time}:00`);
    await addBlackout(d.toISOString(), note.trim() || "Unavailable");
    setNote("");
    toast("Blackout added");
  };

  return (
    <div className="grid gap-12 lg:grid-cols-2">
      <section>
        <h1 className="text-2xl">Weekly hours</h1>
        <p className="mt-1 text-sm text-slate">Click a time to turn it on or off.</p>
        <div className="mt-5 space-y-3">
          {DAYS.map(([day, label]) => (
            <div key={day} className="flex flex-wrap items-center gap-2">
              <span className="w-24 text-sm text-slate">{label}</span>
              {ROW_TIMES.map((t) => {
                const on = (state.hours[day] ?? []).includes(t);
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => toggle(day, t)}
                    className={`tnum border px-2 py-1 text-xs ${
                      on ? "border-felt bg-felt text-felt-foreground" : "border-border text-slate"
                    }`}
                  >
                    {t}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-2xl">Blackouts</h2>
        <div className="mt-5 flex flex-wrap items-end gap-2">
          <label className="text-sm text-slate">
            Date
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="tnum mt-1 block border border-input bg-transparent px-2 py-1.5 text-foreground outline-none focus:border-felt"
            />
          </label>
          <label className="text-sm text-slate">
            Time
            <select
              value={time}
              onChange={(e) => setTime(e.target.value)}
              className="tnum mt-1 block border border-input bg-transparent px-2 py-1.5 text-foreground outline-none focus:border-felt"
            >
              {ROW_TIMES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm text-slate">
            Note
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Dentist"
              className="mt-1 block border border-input bg-transparent px-2 py-1.5 text-foreground outline-none focus:border-felt"
            />
          </label>
          <button onClick={add} className="bg-felt px-3 py-2 text-sm text-felt-foreground">
            Add blackout
          </button>
        </div>

        <ul className="mt-6 divide-y divide-border border-t border-b border-border">
          {state.blackouts.length === 0 && (
            <li className="py-3 text-sm text-slate">No blackouts.</li>
          )}
          {state.blackouts
            .slice()
            .sort((a, b) => a.startsAt.localeCompare(b.startsAt))
            .map((b) => (
              <li key={b.id} className="flex items-center justify-between py-3">
                <div>
                  <p className="tnum text-sm">
                    {fmt.day(b.startsAt)} {fmt.dateShort(b.startsAt)} · {fmt.time(b.startsAt)}
                  </p>
                  <p className="text-sm text-slate">{b.note}</p>
                </div>
                <button
                  onClick={async () => {
                    await removeBlackout(b.id);
                    toast("Blackout removed");
                  }}
                  className="text-sm text-felt underline underline-offset-4"
                >
                  Remove
                </button>
              </li>
            ))}
        </ul>
      </section>
    </div>
  );
}
