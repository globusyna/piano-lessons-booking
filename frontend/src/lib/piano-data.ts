/**
 * Fixture-backed data layer for the piano lesson calendar.
 * Mirrors the API contracts in the brief. Swap these functions for fetch()
 * calls when the real backend exists — the shapes are identical.
 */

export type StudentStatus = "active" | "paused" | "flagged";

export type Lesson = {
  id: number;
  seq: number;
  studentId: number;
  startsAt: string;
  status: "scheduled" | "done";
};

export type Student = {
  id: number;
  name: string;
  status: StudentStatus;
  token: string;
  slotDay: number; // 1 = Monday ... 5 = Friday
  slotTime: string; // "16:00"
  pkg: { size: number; used: number; periodNo: number };
  invoiceSent: boolean;
};

export type Blackout = { id: number; startsAt: string; note: string };

export type ApiError = {
  code:
    | "SLOT_TAKEN"
    | "DAY_LOCKED"
    | "OUTSIDE_WINDOW"
    | "STUDENT_PAUSED"
    | "STUDENT_FLAGGED"
    | "INVALID_TOKEN";
  message: string;
};

export type Result<T> = { ok: true; data: T } | { ok: false; error: ApiError };

export const ROW_TIMES = [
  "14:00",
  "14:45",
  "15:30",
  "16:15",
  "17:00",
  "17:45",
  "18:30",
];

const DAY_MS = 86400000;

function startOfWeek(d: Date) {
  const date = new Date(d);
  date.setHours(0, 0, 0, 0);
  const diff = (date.getDay() + 6) % 7;
  date.setDate(date.getDate() - diff);
  return date;
}

function iso(date: Date, time: string) {
  const parts = time.split(":").map(Number);
  const d = new Date(date);
  d.setHours(parts[0] ?? 0, parts[1] ?? 0, 0, 0);
  return d.toISOString();
}

export function dateKey(isoStr: string) {
  const d = new Date(isoStr);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

export function timeOf(isoStr: string) {
  const d = new Date(isoStr);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

const BASE = startOfWeek(new Date());

const studentSeed: Array<Omit<Student, "id" | "invoiceSent">> = [
  {
    name: "Anna Lie",
    status: "active",
    token: "anna",
    slotDay: 2,
    slotTime: "16:15",
    pkg: { size: 10, used: 7, periodNo: 3 },
  },
  {
    name: "Jonas Berg",
    status: "active",
    token: "jonas",
    slotDay: 1,
    slotTime: "15:30",
    pkg: { size: 10, used: 10, periodNo: 2 },
  },
  {
    name: "Mira Solheim",
    status: "paused",
    token: "mira",
    slotDay: 3,
    slotTime: "17:00",
    pkg: { size: 8, used: 4, periodNo: 1 },
  },
  {
    name: "Teodor Haugen",
    status: "flagged",
    token: "teodor",
    slotDay: 4,
    slotTime: "14:45",
    pkg: { size: 10, used: 3, periodNo: 5 },
  },
  {
    name: "Selma Ruud",
    status: "active",
    token: "selma",
    slotDay: 5,
    slotTime: "17:45",
    pkg: { size: 10, used: 2, periodNo: 1 },
  },
  {
    name: "Oskar Dahl",
    status: "active",
    token: "oskar",
    slotDay: 2,
    slotTime: "18:30",
    pkg: { size: 10, used: 9, periodNo: 4 },
  },
];

type State = {
  students: Student[];
  lessons: Lesson[];
  blackouts: Blackout[];
  hours: Record<number, string[]>; // day -> available times
  contestedSlot: string | null;
};

function buildState(): State {
  const students: Student[] = studentSeed.map((s, i) => ({
    ...s,
    id: i + 1,
    invoiceSent: false,
  }));

  const lessons: Lesson[] = [];
  let id = 400;
  for (const s of students) {
    const remaining = s.pkg.size - s.pkg.used;
    // past lessons, one per week backwards
    for (let k = s.pkg.used; k >= 1; k--) {
      const weeksBack = s.pkg.used - k + 1;
      const d = new Date(BASE.getTime() + (s.slotDay - 1) * DAY_MS - weeksBack * 7 * DAY_MS);
      lessons.push({
        id: ++id,
        seq: k,
        studentId: s.id,
        startsAt: iso(d, s.slotTime),
        status: "done",
      });
    }
    for (let k = 0; k < remaining; k++) {
      const d = new Date(BASE.getTime() + (s.slotDay - 1) * DAY_MS + k * 7 * DAY_MS);
      lessons.push({
        id: ++id,
        seq: s.pkg.used + k + 1,
        studentId: s.id,
        startsAt: iso(d, s.slotTime),
        status: "scheduled",
      });
    }
  }

  const blackouts: Blackout[] = [
    {
      id: 1,
      startsAt: iso(new Date(BASE.getTime() + 2 * DAY_MS), "17:00"),
      note: "Dentist",
    },
    {
      id: 2,
      startsAt: iso(new Date(BASE.getTime() + 2 * DAY_MS), "17:45"),
      note: "Dentist",
    },
    {
      id: 3,
      startsAt: iso(new Date(BASE.getTime() + 8 * DAY_MS), "14:00"),
      note: "Recital rehearsal",
    },
  ];

  const hours: Record<number, string[]> = {
    1: ROW_TIMES.slice(1),
    2: ROW_TIMES,
    3: ROW_TIMES.slice(0, 6),
    4: ROW_TIMES,
    5: ROW_TIMES.slice(0, 5),
  };

  const contested = iso(new Date(BASE.getTime() + 8 * DAY_MS), "15:30");

  return { students, lessons, blackouts, hours, contestedSlot: contested };
}

let state: State = buildState();
const listeners = new Set<() => void>();

function emit() {
  state = { ...state };
  listeners.forEach((l) => l());
}

export function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function getState() {
  return state;
}

const wait = (ms = 220) => new Promise((r) => setTimeout(r, ms));

export function isDayLocked(isoStr: string) {
  const d = new Date(isoStr);
  d.setHours(0, 0, 0, 0);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return d.getTime() <= today.getTime();
}

function inMoveWindow(isoStr: string) {
  const t = new Date(isoStr).getTime();
  const now = Date.now();
  return t > now && t < now + 21 * DAY_MS;
}

// ---------- student surface ----------

export type StudentView = {
  student: { id: number; name: string; status: StudentStatus };
  package: { size: number; used: number; periodNo: number };
  nextLesson: { id: number; seq: number; startsAt: string; canMove: boolean } | null;
  lessons: Array<{
    id: number;
    seq: number;
    startsAt: string;
    status: string;
    canMove: boolean;
  }>;
  canRequestPause: boolean;
};

export function getStudentView(token: string): Result<StudentView> {
  const s = state.students.find((x) => x.token === token);
  if (!s)
    return {
      ok: false,
      error: { code: "INVALID_TOKEN", message: "This link isn't valid. Ask your teacher for a new one." },
    };
  const actionable = s.status === "active";
  const upcoming = state.lessons
    .filter(
      (l) =>
        l.studentId === s.id &&
        l.status === "scheduled" &&
        new Date(l.startsAt).getTime() > Date.now(),
    )
    .sort((a, b) => +new Date(a.startsAt) - +new Date(b.startsAt))
    .map((l) => ({
      id: l.id,
      seq: l.seq,
      startsAt: l.startsAt,
      status: l.status,
      canMove: actionable && !isDayLocked(l.startsAt),
    }));
  return {
    ok: true,
    data: {
      student: { id: s.id, name: s.name, status: s.status },
      package: s.pkg,
      nextLesson: upcoming[0] ?? null,
      lessons: upcoming,
      canRequestPause: actionable && upcoming.length > 0,
    },
  };
}

export function getOpenSlots(excludeLessonId?: number): string[] {
  const taken = new Set(
    state.lessons
      .filter((l) => l.status === "scheduled" && l.id !== excludeLessonId)
      .map((l) => l.startsAt),
  );
  const blocked = new Set(state.blackouts.map((b) => b.startsAt));
  const out: string[] = [];
  for (let offset = 0; offset < 28; offset++) {
    const d = new Date(BASE.getTime() + offset * DAY_MS);
    const day = ((d.getDay() + 6) % 7) + 1;
    const times = state.hours[day] ?? [];
    for (const t of times) {
      const s = iso(d, t);
      if (taken.has(s) || blocked.has(s)) continue;
      if (!inMoveWindow(s)) continue;
      if (isDayLocked(s)) continue;
      out.push(s);
    }
  }
  return out.sort();
}

export async function moveLesson(lessonId: number, startsAt: string): Promise<Result<Lesson>> {
  await wait();
  const lesson = state.lessons.find((l) => l.id === lessonId);
  if (!lesson)
    return { ok: false, error: { code: "SLOT_TAKEN", message: "That lesson is no longer available." } };
  const student = state.students.find((s) => s.id === lesson.studentId)!;
  if (student.status === "paused")
    return {
      ok: false,
      error: { code: "STUDENT_PAUSED", message: "Your lessons are paused. Your teacher will be in touch." },
    };
  if (student.status === "flagged")
    return {
      ok: false,
      error: { code: "STUDENT_FLAGGED", message: "There's an open question on your account. Your teacher will be in touch." },
    };
  if (isDayLocked(lesson.startsAt))
    return { ok: false, error: { code: "DAY_LOCKED", message: "That day is closed for changes." } };
  if (!inMoveWindow(startsAt))
    return { ok: false, error: { code: "OUTSIDE_WINDOW", message: "That time is outside the booking window." } };
  if (state.contestedSlot === startsAt) {
    state.contestedSlot = null;
    state.blackouts.push({ id: Date.now(), startsAt, note: "Booked by someone else" });
    emit();
    return {
      ok: false,
      error: { code: "SLOT_TAKEN", message: "Someone just took that time. Here are the times still open." },
    };
  }
  if (state.lessons.some((l) => l.startsAt === startsAt && l.status === "scheduled"))
    return { ok: false, error: { code: "SLOT_TAKEN", message: "Someone just took that time. Here are the times still open." } };
  lesson.startsAt = startsAt;
  emit();
  return { ok: true, data: lesson };
}

export async function requestPause(studentId: number): Promise<Result<Student>> {
  await wait();
  const s = state.students.find((x) => x.id === studentId)!;
  s.status = "paused";
  emit();
  return { ok: true, data: s };
}

// ---------- admin surface ----------

export type WeekCell =
  | {
      type: "lesson";
      startsAt: string;
      lessonId: number;
      studentName: string;
      seq: number;
      size: number;
    }
  | { type: "blackout"; startsAt: string; note: string }
  | { type: "open"; startsAt: string };

export type WeekDay = { date: string; locked: boolean; cells: WeekCell[] };

export function getWeek(weekOffset: number): WeekDay[] {
  const days: WeekDay[] = [];
  for (let i = 0; i < 5; i++) {
    const d = new Date(BASE.getTime() + (weekOffset * 7 + i) * DAY_MS);
    const cells: WeekCell[] = [];
    for (const t of ROW_TIMES) {
      const s = iso(d, t);
      const lesson = state.lessons.find((l) => l.startsAt === s && l.status !== "done");
      const black = state.blackouts.find((b) => b.startsAt === s);
      if (lesson) {
        const st = state.students.find((x) => x.id === lesson.studentId)!;
        cells.push({
          type: "lesson",
          startsAt: s,
          lessonId: lesson.id,
          studentName: st.name,
          seq: lesson.seq,
          size: st.pkg.size,
        });
      } else if (black) {
        cells.push({ type: "blackout", startsAt: s, note: black.note });
      } else {
        cells.push({ type: "open", startsAt: s });
      }
    }
    days.push({ date: dateKey(s0(d)), locked: isDayLocked(s0(d)), cells });
  }
  return days;
}

function s0(d: Date) {
  const x = new Date(d);
  x.setHours(12, 0, 0, 0);
  return x.toISOString();
}

export function weekStart(offset: number) {
  return new Date(BASE.getTime() + offset * 7 * DAY_MS);
}

export async function removeLesson(lessonId: number) {
  await wait(120);
  state.lessons = state.lessons.filter((l) => l.id !== lessonId);
  emit();
  return { ok: true as const };
}

export async function addBlackout(startsAt: string, note: string) {
  await wait(120);
  state.blackouts.push({ id: Date.now(), startsAt, note });
  emit();
  return { ok: true as const };
}

export async function removeBlackout(id: number) {
  await wait(120);
  state.blackouts = state.blackouts.filter((b) => b.id !== id);
  emit();
  return { ok: true as const };
}

export async function setHours(day: number, times: string[]) {
  await wait(80);
  state.hours = { ...state.hours, [day]: times };
  emit();
  return { ok: true as const };
}

export async function setStudentStatus(id: number, status: StudentStatus) {
  await wait(120);
  const s = state.students.find((x) => x.id === id)!;
  s.status = status;
  emit();
  return { ok: true as const };
}

export async function setWeeklySlot(id: number, slotDay: number, slotTime: string) {
  await wait(120);
  const s = state.students.find((x) => x.id === id)!;
  s.slotDay = slotDay;
  s.slotTime = slotTime;
  emit();
  return { ok: true as const };
}

export async function markInvoiceSent(id: number) {
  await wait(120);
  const s = state.students.find((x) => x.id === id)!;
  s.invoiceSent = true;
  emit();
  return { ok: true as const };
}

export async function openPackage(id: number, size: number) {
  await wait(160);
  const s = state.students.find((x) => x.id === id)!;
  s.pkg = { size, used: 0, periodNo: s.pkg.periodNo + 1 };
  s.invoiceSent = false;
  let maxId = Math.max(...state.lessons.map((l) => l.id));
  const startWeek = 1;
  for (let k = 0; k < size; k++) {
    const d = new Date(BASE.getTime() + (s.slotDay - 1) * DAY_MS + (startWeek + k) * 7 * DAY_MS);
    state.lessons.push({
      id: ++maxId,
      seq: k + 1,
      studentId: s.id,
      startsAt: iso(d, s.slotTime),
      status: "scheduled",
    });
  }
  emit();
  return { ok: true as const };
}

export function lessonHistory(studentId: number) {
  return state.lessons
    .filter((l) => l.studentId === studentId)
    .sort((a, b) => +new Date(a.startsAt) - +new Date(b.startsAt));
}

export function alerts() {
  return state.students.filter((s) => s.pkg.used >= s.pkg.size && !s.invoiceSent);
}

// ---------- formatting ----------

const dayFmt = new Intl.DateTimeFormat("en-GB", { weekday: "long" });
const dayShortFmt = new Intl.DateTimeFormat("en-GB", { weekday: "short" });
const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long" });
const dateShortFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });

export const fmt = {
  day: (s: string) => dayFmt.format(new Date(s)),
  dayShort: (s: string) => dayShortFmt.format(new Date(s)),
  date: (s: string) => dateFmt.format(new Date(s)),
  dateShort: (s: string) => dateShortFmt.format(new Date(s)),
  time: (s: string) => timeOf(s),
};
