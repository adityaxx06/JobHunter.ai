// Skills manager: list, add, edit level/learning, remove (unique names kept).
import { useState } from "react";
import { addSkill, deleteSkill, patchSkill } from "@/lib/api";
import type { ProfileSkill } from "@/types/job";
import { BTN_DANGER, BTN_GHOST, BTN_PRIMARY, FieldError, INPUT, LABEL, Section } from "./common";
import type { SaveState } from "./ProfileSaveState";

const LEVELS = ["beginner", "intermediate", "advanced", "expert"];

export function ProfileSkills({
  skills,
  onChanged,
  onSaveState,
}: {
  skills: ProfileSkill[];
  onChanged: (next: ProfileSkill[]) => void;
  onSaveState: (state: SaveState) => void;
}) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editLevel, setEditLevel] = useState("");
  const [editLearning, setEditLearning] = useState(false);

  async function add() {
    const clean = name.trim();
    if (!clean) {
      setError("Enter a skill name first.");
      return;
    }
    setBusy(true);
    setError(null);
    onSaveState({ kind: "saving", label: "Adding skill…" });
    try {
      const result = await addSkill(undefined, { skill_name: clean });
      if (!result.duplicate) onChanged([...skills, result.skill]);
      onSaveState({ kind: "saved", label: result.duplicate ? "Skill already on your profile." : "Skill added." });
      setName("");
    } catch {
      setError("Could not add the skill. Try again.");
      onSaveState({ kind: "error", label: "Add skill failed." });
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    setError(null);
    try {
      const result = await deleteSkill(undefined, id);
      if (result.deleted) {
        onChanged(skills.filter((skill) => skill.id !== id));
        onSaveState({ kind: "saved", label: "Skill removed." });
      }
    } catch {
      setError("Could not remove the skill. Try again.");
      onSaveState({ kind: "error", label: "Remove skill failed." });
    } finally {
      setBusy(false);
    }
  }

  function startEdit(skill: ProfileSkill) {
    setEditingId(skill.id);
    setEditLevel(skill.skill_level ?? "");
    setEditLearning(skill.is_learning);
    setError(null);
  }

  async function saveEdit(skill: ProfileSkill) {
    setBusy(true);
    setError(null);
    try {
      const next = await patchSkill(undefined, skill.id, {
        skill_level: editLevel.trim() || null,
        is_learning: editLearning,
      });
      onChanged(skills.map((item) => (item.id === skill.id ? next : item)));
      setEditingId(null);
      onSaveState({ kind: "saved", label: "Skill updated." });
    } catch {
      setError("Could not update the skill. Try again.");
      onSaveState({ kind: "error", label: "Update skill failed." });
    } finally {
      setBusy(false);
    }
  }

  const owned = skills.filter((skill) => !skill.is_learning);
  const learning = skills.filter((skill) => skill.is_learning);

  function row(skill: ProfileSkill) {
    const editing = editingId === skill.id;
    return (
      <li
        key={skill.id}
        className="flex flex-wrap items-center gap-2 rounded-lg border border-line-soft bg-ink-850 px-3 py-2"
      >
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-100">{skill.skill_name}</span>
        {editing ? (
          <>
            <select
              aria-label={`Level for ${skill.skill_name}`}
              className="rounded-lg border border-line bg-ink-900 px-2 py-1 text-xs text-zinc-200 focus:outline-none"
              value={editLevel}
              disabled={busy}
              onChange={(event) => setEditLevel(event.target.value)}
            >
              <option value="">No level</option>
              {LEVELS.map((level) => (
                <option key={level} value={level}>
                  {level}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-1.5 text-xs text-fog">
              <input
                type="checkbox"
                checked={editLearning}
                disabled={busy}
                onChange={(event) => setEditLearning(event.target.checked)}
                className="h-3.5 w-3.5 accent-[#7C6CFF]"
              />
              Learning
            </label>
            <button type="button" className={BTN_GHOST} disabled={busy} onClick={() => saveEdit(skill)}>
              Save
            </button>
            <button type="button" className={BTN_GHOST} disabled={busy} onClick={() => setEditingId(null)}>
              Cancel
            </button>
          </>
        ) : (
          <>
            <span className="rounded-md border border-line-soft bg-ink-900 px-2 py-0.5 text-xs text-zinc-300">
              {skill.is_learning ? "learning" : skill.skill_level || "no level"}
            </span>
            <button type="button" className={BTN_GHOST} disabled={busy} onClick={() => startEdit(skill)}>
              Edit
            </button>
            <button type="button" className={BTN_DANGER} disabled={busy} onClick={() => remove(skill.id)}>
              Remove
            </button>
          </>
        )}
      </li>
    );
  }

  return (
    <Section
      title="Skills"
      blurb="What you know and what you are learning — drives match scoring."
    >
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="flex-1">
          <label className={LABEL} htmlFor="skill-name">
            New skill
          </label>
          <input
            id="skill-name"
            className={INPUT}
            value={name}
            disabled={busy}
            placeholder="e.g. TypeScript"
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") add();
            }}
          />
        </div>
        <div className="flex items-end">
          <button type="button" className={BTN_PRIMARY} disabled={busy || !name.trim()} onClick={add}>
            {busy ? "Adding…" : "Add skill"}
          </button>
        </div>
      </div>
      <FieldError message={error} />
      {skills.length === 0 ? (
        <p className="mt-4 text-sm text-fog">No skills yet — add your first one above.</p>
      ) : (
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-fog">
              Proficient ({owned.length})
            </h3>
            <ul className="space-y-2">{owned.map(row)}</ul>
          </div>
          <div>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-fog">
              Learning ({learning.length})
            </h3>
            {learning.length === 0 ? (
              <p className="text-sm text-fog-faint">Nothing marked as learning.</p>
            ) : (
              <ul className="space-y-2">{learning.map(row)}</ul>
            )}
          </div>
        </div>
      )}
    </Section>
  );
}
