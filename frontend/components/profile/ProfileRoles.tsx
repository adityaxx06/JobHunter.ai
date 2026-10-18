// Target-role manager: list, add, rename, priority, remove.
import { useState } from "react";
import { addRole, deleteRole, patchRole } from "@/lib/api";
import type { ProfileRole } from "@/types/job";
import { BTN_DANGER, BTN_GHOST, BTN_PRIMARY, FieldError, INPUT, LABEL, Section } from "./common";
import type { SaveState } from "./ProfileSaveState";

export function ProfileRoles({
  roles,
  onChanged,
  onSaveState,
}: {
  roles: ProfileRole[];
  onChanged: (next: ProfileRole[]) => void;
  onSaveState: (state: SaveState) => void;
}) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add() {
    const clean = name.trim();
    if (!clean) {
      setError("Enter a role name first.");
      return;
    }
    setBusy(true);
    setError(null);
    onSaveState({ kind: "saving", label: "Adding role…" });
    try {
      const result = await addRole(undefined, { role_name: clean });
      if (!result.duplicate) onChanged([...roles, result.role]);
      onSaveState({ kind: "saved", label: result.duplicate ? "Role already targeted." : "Role added." });
      setName("");
    } catch {
      setError("Could not add the role. Try again.");
      onSaveState({ kind: "error", label: "Add role failed." });
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      const result = await deleteRole(undefined, id);
      if (result.deleted) {
        onChanged(roles.filter((role) => role.id !== id));
        onSaveState({ kind: "saved", label: "Role removed." });
      }
    } catch {
      setError("Could not remove the role. Try again.");
      onSaveState({ kind: "error", label: "Remove role failed." });
    } finally {
      setBusy(false);
    }
  }

  async function setPriority(role: ProfileRole, priority: number) {
    if (!role.id || !Number.isInteger(priority) || priority < 1) return;
    setBusy(true);
    setError(null);
    try {
      const next = await patchRole(undefined, role.id, { priority });
      onChanged(roles.map((item) => (item.id === role.id ? next : item)));
      onSaveState({ kind: "saved", label: "Priority updated." });
    } catch {
      setError("Could not update priority. Try again.");
      onSaveState({ kind: "error", label: "Update priority failed." });
    } finally {
      setBusy(false);
    }
  }

  const sorted = [...roles].sort((a, b) => (a.priority ?? 1) - (b.priority ?? 1));

  return (
    <Section title="Target roles" blurb="Roles discovery searches for, highest priority first.">
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="flex-1">
          <label className={LABEL} htmlFor="role-name">
            New role
          </label>
          <input
            id="role-name"
            className={INPUT}
            value={name}
            disabled={busy}
            placeholder="e.g. Java Developer"
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") add();
            }}
          />
        </div>
        <div className="flex items-end">
          <button type="button" className={BTN_PRIMARY} disabled={busy || !name.trim()} onClick={add}>
            {busy ? "Adding…" : "Add role"}
          </button>
        </div>
      </div>
      <FieldError message={error} />
      {sorted.length === 0 ? (
        <p className="mt-4 text-sm text-fog">No target roles yet.</p>
      ) : (
        <ul className="mt-4 space-y-2">
          {sorted.map((role) => (
            <li
              key={role.id ?? role.role_name}
              className="flex flex-wrap items-center gap-2 rounded-lg border border-line-soft bg-ink-850 px-3 py-2"
            >
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-100">{role.role_name}</span>
              <label className="flex items-center gap-1.5 text-xs text-fog">
                Priority
                <input
                  type="number"
                  min={1}
                  max={100}
                  className="w-16 rounded-lg border border-line bg-ink-900 px-2 py-1 text-xs text-zinc-200 focus:outline-none"
                  value={role.priority ?? 1}
                  disabled={busy || !role.id}
                  onChange={(event) => setPriority(role, Number(event.target.value))}
                />
              </label>
              <button type="button" className={BTN_DANGER} disabled={busy || !role.id} onClick={() => remove(role.id ?? "")}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
