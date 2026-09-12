import { useSyncExternalStore } from "react";
import { getState, subscribe } from "@/lib/piano-data";

export function usePianoStore() {
  return useSyncExternalStore(
    (cb) => subscribe(cb),
    () => getState(),
    () => getState(),
  );
}
