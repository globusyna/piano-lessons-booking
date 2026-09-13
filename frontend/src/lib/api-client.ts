import type {
  AdminAlert,
  Blackout,
  Lesson,
  LessonMoveRequest,
  Package,
  Student,
  StudentStatus,
  StudentView,
  WeekDay,
} from "@/lib/piano-data";

const API_BASE_URL = (import.meta.env["VITE_API_BASE_URL"] ?? "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);
const ADMIN_TOKEN_KEY = "piano-admin-token";

export class ApiClientError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

type ErrorBody = { error?: { code?: string; message?: string } };

export function getAdminToken() {
  return typeof window === "undefined" ? null : sessionStorage.getItem(ADMIN_TOKEN_KEY);
}

export function setAdminToken(token: string) {
  sessionStorage.setItem(ADMIN_TOKEN_KEY, token);
}

export function clearAdminToken() {
  sessionStorage.removeItem(ADMIN_TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}, admin = false): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (admin) {
    const token = getAdminToken();
    if (!token) throw new ApiClientError(401, "UNAUTHENTICATED", "Please sign in.");
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiClientError(
      0,
      "NETWORK_ERROR",
      "Could not reach the booking server. Check that the backend is running.",
    );
  }

  const body = (await response.json().catch(() => null)) as (T & ErrorBody) | null;
  if (!response.ok) {
    if (response.status === 401 && admin) {
      clearAdminToken();
      window.dispatchEvent(new Event("piano-admin-unauthenticated"));
    }
    throw new ApiClientError(
      response.status,
      body?.error?.code ?? "REQUEST_ERROR",
      body?.error?.message ?? "The request failed.",
    );
  }
  return body as T;
}

const json = (value: unknown) => JSON.stringify(value);
const studentPath = (token: string) => `/s/${encodeURIComponent(token)}`;

export async function login(password: string) {
  const response = await request<{ accessToken: string }>("/auth/token", {
    method: "POST",
    body: json({ username: "admin", password }),
  });
  setAdminToken(response.accessToken);
}

export const api = {
  studentView: (token: string) => request<StudentView>(studentPath(token)),
  openSlots: async (token: string, lessonId: number) => {
    const from = new Date();
    const to = new Date(from);
    to.setDate(to.getDate() + 21);
    const params = new URLSearchParams({
      from: localDate(from),
      to: localDate(to),
      lessonId: String(lessonId),
    });
    const response = await request<{ slots: Array<{ startsAt: string }> }>(
      `${studentPath(token)}/slots?${params}`,
    );
    return response.slots.map((slot) => slot.startsAt);
  },
  moveLesson: (token: string, lessonId: number, startsAt: string) =>
    request<{ ok: true; data: LessonMoveRequest }>(
      `${studentPath(token)}/lessons/${lessonId}/reschedule`,
      {
        method: "POST",
        body: json({ startsAt }),
      },
    ),
  requestPause: (token: string, weeks: number) =>
    request<{ ok: true; data: Student }>(`${studentPath(token)}/pause-request`, {
      method: "POST",
      body: json({ weeks }),
    }),

  week: async (start: string) =>
    (await request<{ days: WeekDay[] }>(`/admin/api/week?start=${start}`, {}, true)).days,
  availability: () =>
    request<{ hours: Record<string, string[]>; blackouts: Blackout[] }>(
      "/admin/availability",
      {},
      true,
    ),
  setHours: (day: number, times: string[]) =>
    request<{ ok: true }>(
      "/admin/availability",
      { method: "POST", body: json({ day, times }) },
      true,
    ),
  addBlackout: (startsAt: string, note: string) =>
    request<{ ok: true; data: Blackout }>(
      "/admin/blackout",
      { method: "POST", body: json({ startsAt, note }) },
      true,
    ),
  removeBlackout: (id: number) =>
    request<{ ok: true }>(`/admin/blackout/${id}`, { method: "DELETE" }, true),
  students: async () =>
    (await request<{ students: Student[] }>("/admin/students", {}, true)).students,
  student: (id: number) =>
    request<{ student: Student; lessons: Lesson[] }>(`/admin/students/${id}`, {}, true),
  pauseStudent: (id: number, weeks: number) =>
    request<{ ok: true; data: Student }>(
      `/admin/students/${id}/pause`,
      { method: "POST", body: json({ weeks }) },
      true,
    ),
  resumeStudent: (id: number) =>
    request<{ ok: true; data: Student }>(`/admin/students/${id}/resume`, { method: "POST" }, true),
  setStudentStatus: (id: number, status: StudentStatus) =>
    request<{ ok: true }>(
      `/admin/students/${id}/status`,
      { method: "POST", body: json({ status }) },
      true,
    ),
  setWeeklySlot: (id: number, slotDay: number, slotTime: string) =>
    request<{ ok: true }>(
      `/admin/students/${id}/slot`,
      { method: "POST", body: json({ slotDay, slotTime }) },
      true,
    ),
  markInvoiceSent: (packageId: number) =>
    request<{ ok: true }>(`/admin/packages/${packageId}/invoiced`, { method: "POST" }, true),
  openPackage: (id: number, size: number) =>
    request<{ ok: true }>(
      `/admin/students/${id}/package`,
      { method: "POST", body: json({ size }) },
      true,
    ),
  // Tops the current package up rather than starting a new one: the lessons
  // already booked keep their dates and `size` goes up by this much.
  renewPackage: (id: number, size: number) =>
    request<{ ok: true }>(
      `/admin/students/${id}/package/renew`,
      { method: "POST", body: json({ size }) },
      true,
    ),
  removeLesson: (id: number) =>
    request<{ ok: true }>(`/admin/lessons/${id}`, { method: "DELETE" }, true),
  approveMoveRequest: (id: number) =>
    request<{ ok: true; data: Lesson }>(
      `/admin/move-requests/${id}/approve`,
      { method: "POST" },
      true,
    ),
  // The declined request comes back, not a bare ok, so the caller can show the
  // answer without a second round trip. `reason` is optional all the way down:
  // null means the teacher gave none.
  declineMoveRequest: (id: number, reason?: string) =>
    request<{ ok: true; data: LessonMoveRequest }>(
      `/admin/move-requests/${id}/decline`,
      { method: "POST", body: json({ reason: reason ?? null }) },
      true,
    ),
  alerts: async () => (await request<{ alerts: AdminAlert[] }>("/admin/alerts", {}, true)).alerts,
};

function localDate(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate(),
  ).padStart(2, "0")}`;
}

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "The request failed.";
}
