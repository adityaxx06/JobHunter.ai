// Save-state indicator for Profile mutations (saving / saved / error).
import { cn } from "@/lib/utils";

export type SaveState =
  | { kind: "idle" }
  | { kind: "saving"; label: string }
  | { kind: "saved"; label: string }
  | { kind: "error"; label: string };

export const IDLE_SAVE: SaveState = { kind: "idle" };

export function ProfileSaveState({ state }: { state: SaveState }) {
  if (state.kind === "idle") return null;
  return (
    <p
      role="status"
      aria-live="polite"
      className={cn(
        "text-sm",
        state.kind === "saving" && "text-caution",
        state.kind === "saved" && "text-positive",
        state.kind === "error" && "text-danger",
      )}
    >
      {state.kind === "saving" && "Saving… "}
      {state.kind === "saved" && "Saved. "}
      {state.label}
    </p>
  );
}
