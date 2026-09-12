export type StudentStatus = "active" | "paused" | "flagged";

export type Package = {
  id: number | null;
  size: number;
  used: number;
  periodNo: number;
};

export type Lesson = {
  id: number;
  seq: number;
  studentId: number;
  startsAt: string;
  status: "scheduled" | "done";
};

export type LessonMoveRequest = {
  id: number;
  lessonId: number;
  requestedStartsAt: string;
};

export type Student = {
  id: number;
  name: string;
  status: StudentStatus;
  token: string;
  slotDay: number;
  slotTime: string;
  pkg: Package;
  invoiceSent: boolean;
};

export type Blackout = { id: number; startsAt: string; note: string };

export type StudentLesson = {
  id: number;
  seq: number;
  startsAt: string;
  status: "scheduled" | "done";
  canMove: boolean;
  requestedStartsAt: string | null;
};

export type StudentView = {
  student: { id: number; name: string; status: StudentStatus };
  package: Package;
  nextLesson: StudentLesson | null;
  lessons: StudentLesson[];
  canRequestPause: boolean;
};

export type AlertStudent = { id: number; name: string; status: StudentStatus };

export type AdminAlert =
  | { type: "moveRequest"; student: AlertStudent; lesson: Lesson; moveRequest: LessonMoveRequest }
  | { type: "invoice"; student: AlertStudent; package: Package };

export type WeekCell =
  | {
      type: "lesson";
      startsAt: string;
      lessonId: number;
      studentName: string;
      seq: number;
      size: number;
      moveRequest: LessonMoveRequest | null;
    }
  | { type: "blackout"; startsAt: string; note: string }
  | { type: "open"; startsAt: string };

export type WeekDay = { date: string; locked: boolean; cells: WeekCell[] };

export const ROW_TIMES = ["14:00", "14:45", "15:30", "16:15", "17:00", "17:45", "18:30"];

const DAY_MS = 86_400_000;

function startOfWeek(date: Date) {
  const result = new Date(date);
  result.setHours(0, 0, 0, 0);
  result.setDate(result.getDate() - ((result.getDay() + 6) % 7));
  return result;
}

export function weekStart(offset: number) {
  return new Date(startOfWeek(new Date()).getTime() + offset * 7 * DAY_MS);
}

export function dateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate(),
  ).padStart(2, "0")}`;
}

function timeOf(iso: string) {
  const date = new Date(iso);
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

const dayFmt = new Intl.DateTimeFormat("en-GB", { weekday: "long" });
const dayShortFmt = new Intl.DateTimeFormat("en-GB", { weekday: "short" });
const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long" });
const dateShortFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });

export const fmt = {
  day: (value: string) => dayFmt.format(new Date(value)),
  dayShort: (value: string) => dayShortFmt.format(new Date(value)),
  date: (value: string) => dateFmt.format(new Date(value)),
  dateShort: (value: string) => dateShortFmt.format(new Date(value)),
  time: timeOf,
};
