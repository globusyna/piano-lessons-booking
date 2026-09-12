import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

export const pianoKeys = {
  all: ["piano"] as const,
  week: (start: string) => [...pianoKeys.all, "week", start] as const,
  availability: () => [...pianoKeys.all, "availability"] as const,
  students: () => [...pianoKeys.all, "students"] as const,
  student: (id: number) => [...pianoKeys.students(), id] as const,
  alerts: () => [...pianoKeys.all, "alerts"] as const,
  studentView: (token: string) => [...pianoKeys.all, "student-view", token] as const,
  slots: (token: string, lessonId: number) =>
    [...pianoKeys.studentView(token), "slots", lessonId] as const,
};

export function useStudents() {
  return useQuery({ queryKey: pianoKeys.students(), queryFn: api.students });
}

export function useStudent(id: number) {
  return useQuery({ queryKey: pianoKeys.student(id), queryFn: () => api.student(id) });
}

export function useAvailability() {
  return useQuery({ queryKey: pianoKeys.availability(), queryFn: api.availability });
}

export function useStudentView(token: string) {
  return useQuery({
    queryKey: pianoKeys.studentView(token),
    queryFn: () => api.studentView(token),
    retry: false,
  });
}

export function useOpenSlots(token: string, lessonId: number | null) {
  return useQuery({
    queryKey: pianoKeys.slots(token, lessonId ?? 0),
    queryFn: () => api.openSlots(token, lessonId!),
    enabled: lessonId !== null,
  });
}
