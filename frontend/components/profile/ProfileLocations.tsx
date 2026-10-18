// Target-location manager: list, add, remote toggle, priority, remove.
import { useState } from "react";
import { addLocation, deleteLocation, patchLocation } from "@/lib/api";
import type { ProfileLocation } from "@/types/job";
import { BTN_DANGER, BTN_GHOST, BTN_PRIMARY, FieldError, INPUT, LABEL, Section } from "./common";
import type { SaveState } from "./ProfileSaveState";

export function ProfileLocations({
  locations,
  onChanged,
  onSaveState,
}: {
  locations: ProfileLocation[];
  onChanged: (next: ProfileLocation[]) => void;
  onSaveState: (state: SaveState) => void;
}) {
  const [name, setName] = useState("");
  const [remote, setRemote] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add() {
    const clean = name.trim();
    if (!clean) {
      setError("Enter a location name first.");
      return;
    }
    setBusy(true);
    setError(null);
    onSaveState({ kind: "saving", label: "Adding location…" });
    try {
      const result = await addLocation(undefined, { location_name: clean, is_remote: remote });
      if (!result.duplicate) onChanged([...locations, result.location]);
      onSaveState({ kind: "saved", label: result.duplicate ? "Location already targeted." : "Location added." });
      setName("");
      setRemote(false);
    } catch {
      setError("Could not add the location. Try again.");
      onSaveState({ kind: "error", label: "Add location failed." });
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      const result = await deleteLocation(undefined, id);
      if (result.deleted) {
        onChanged(locations.filter((location) => location.id !== id));
        onSaveState({ kind: "saved", label: "Location removed." });
      }
    } catch {
      setError("Could not remove the location. Try again.");
      onSaveState({ kind: "error", label: "Remove location failed." });
    } finally {
      setBusy(false);
    }
  }

  async function update(id: string, body: { is_remote?: boolean; priority?: number }, label: string) {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      const next = await patchLocation(undefined, id, body);
      onChanged(locations.map((item) => (item.id === id ? next : item)));
      onSaveState({ kind: "saved", label });
    } catch {
      setError("Could not update the location. Try again.");
      onSaveState({ kind: "error", label: "Update location failed." });
    } finally {
      setBusy(false);
    }
  }

  const sorted = [...locations].sort((a, b) => (a.priority ?? 1) - (b.priority ?? 1));

  return (
    <Section title="Target locations" blurb="Where discovery searches, highest priority first.">
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="flex-1">
          <label className={LABEL} htmlFor="location-name">
            New location
          </label>
          <input
            id="location-name"
            className={INPUT}
            value={name}
            disabled={busy}
            placeholder="e.g. Chennai"
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") add();
            }}
          />
        </div>
        <label className="flex items-center gap-2 self-end rounded-lg border border-line bg-ink-850 px-3 py-2 text-sm text-zinc-200">
          <input
            type="checkbox"
            checked={remote}
            disabled={busy}
            onChange={(event) => setRemote(event.target.checked)}
            className="h-4 w-4 accent-[#7C6CFF]"
          />
          Remote
        </label>
        <div className="flex items-end">
          <button type="button" className={BTN_PRIMARY} disabled={busy || !name.trim()} onClick={add}>
            {busy ? "Adding…" : "Add"}
          </button>
        </div>
      </div>
      <FieldError message={error} />
      {sorted.length === 0 ? (
        <p className="mt-4 text-sm text-fog">No target locations yet.</p>
      ) : (
        <ul className="mt-4 space-y-2">
          {sorted.map((location) => (
            <li
              key={location.id ?? location.location_name}
              className="flex flex-wrap items-center gap-2 rounded-lg border border-line-soft bg-ink-850 px-3 py-2"
            >
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-100">
                {location.location_name}
              </span>
              <button
                type="button"
                className={BTN_GHOST}
                disabled={busy || !location.id}
                title={location.is_remote ? "Marked remote — click to unmark" : "Mark as remote"}
                onClick={() => update(location.id ?? "", { is_remote: !location.is_remote }, "Remote flag updated.")}
              >
                {location.is_remote ? "Remote ✓" : "On-site"}
              </button>
              <label className="flex items-center gap-1.5 text-xs text-fog">
                Priority
                <input
                  type="number"
                  min={1}
                  max={100}
                  className="w-16 rounded-lg border border-line bg-ink-900 px-2 py-1 text-xs text-zinc-200 focus:outline-none"
                  value={location.priority ?? 1}
                  disabled={busy || !location.id}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    if (Number.isInteger(value) && value >= 1)
                      update(location.id ?? "", { priority: value }, "Priority updated.");
                  }}
                />
              </label>
              <button
                type="button"
                className={BTN_DANGER}
                disabled={busy || !location.id}
                onClick={() => remove(location.id ?? "")}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
