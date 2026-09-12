import type { ReactNode } from "react";
import { ROW_TIMES, fmt, type WeekCell, type WeekDay } from "@/lib/piano-data";
import { cn } from "@/lib/utils";

export function LessonChip({
  title,
  subtitle,
  time,
  className,
}: {
  title: string;
  subtitle?: string;
  time: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex h-full w-full flex-col justify-center bg-felt px-2 py-1 text-left text-felt-foreground",
        className,
      )}
    >
      <span className="truncate text-sm leading-tight">{title}</span>
      <span className="tnum text-[11px] leading-tight opacity-80">
        {time}
        {subtitle ? ` · ${subtitle}` : ""}
      </span>
    </div>
  );
}

type Props = {
  days: WeekDay[];
  /** Wrap a lesson cell, e.g. in a popover trigger (admin). */
  renderLesson?:
    ((cell: Extract<WeekCell, { type: "lesson" }>, chip: ReactNode) => ReactNode) | undefined;
  /** Click handler for open cells (read-only grids pass nothing). */
  onOpenClick?: ((startsAt: string) => void) | undefined;
  /** Label a lesson chip (admin shows names, student shows numbers). */
  lessonTitle?: ((cell: Extract<WeekCell, { type: "lesson" }>) => string) | undefined;
};

export function TimeGrid({ days, renderLesson, onOpenClick, lessonTitle }: Props) {
  return (
    <div className="w-full overflow-x-auto">
      <div className="min-w-[720px]">
        <div
          className="grid border-t border-l border-border"
          style={{ gridTemplateColumns: `4.5rem repeat(${days.length}, minmax(0, 1fr))` }}
        >
          <div className="border-r border-b border-border" />
          {days.map((d) => (
            <div key={d.date} className="border-r border-b border-border px-2 py-2">
              <div className="text-sm">{fmt.dayShort(d.date)}</div>
              <div className="tnum text-xs text-muted-foreground">{fmt.dateShort(d.date)}</div>
            </div>
          ))}

          {ROW_TIMES.map((time, row) => (
            <Row
              key={time}
              time={time}
              row={row}
              days={days}
              renderLesson={renderLesson}
              onOpenClick={onOpenClick}
              lessonTitle={lessonTitle}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function Row({
  time,
  row,
  days,
  renderLesson,
  onOpenClick,
  lessonTitle,
}: Props & { time: string; row: number }) {
  return (
    <>
      <div className="tnum border-r border-b border-border px-2 py-2 text-xs text-muted-foreground">
        {time}
      </div>
      {days.map((d) => {
        const cell = d.cells[row];
        if (!cell)
          return <div key={d.date + time} className="h-14 border-r border-b border-border" />;

        if (cell.type === "lesson") {
          const chip = (
            <LessonChip
              title={lessonTitle ? lessonTitle(cell) : cell.studentName}
              subtitle={`${cell.seq}/${cell.size}${cell.moveRequest ? " · Move request" : ""}`}
              time={fmt.time(cell.startsAt)}
            />
          );
          return (
            <div key={cell.startsAt} className="h-14 border-r border-b border-border p-0">
              {renderLesson ? renderLesson(cell, chip) : chip}
            </div>
          );
        }

        if (cell.type === "blackout") {
          return (
            <div
              key={cell.startsAt}
              className="flex h-14 items-center border-r border-b border-border bg-blackout px-2"
              title={cell.note}
            >
              <span className="truncate text-xs text-muted-foreground">{cell.note}</span>
            </div>
          );
        }

        return (
          <div key={cell.startsAt} className="h-14 border-r border-b border-border">
            {onOpenClick ? (
              <button
                type="button"
                onClick={() => onOpenClick(cell.startsAt)}
                className="h-full w-full cursor-pointer"
                aria-label={`Open slot ${fmt.dayShort(cell.startsAt)} ${fmt.time(cell.startsAt)}`}
              />
            ) : null}
          </div>
        );
      })}
    </>
  );
}
