// Job preferences: experience level, work mode, relocation, stipend
// (existing scalar columns only — nothing invented).
import { useState } from "react";
import { patchProfile } from "@/lib/api";
import type { ProfileScalar } from "@/types/job";
import { BTN_PRIMARY, FieldError, INPUT, LABEL, Section } from "./common";
import type { SaveState } from "./ProfileSaveState";

export function ProfilePreferences({
  profile,
  onSaved,
  onSaveState,
}: {
  profile: ProfileScalar;
  onSaved: (next: ProfileScalar) => void;
  onSaveState: (state: SaveState) => void;
}) {
  const [experience, setExperience] = useState(profile.experience_level ?? "");
  const [workMode, setWorkMode] = useState(profile.preferred_work_mode ?? "");
  const [relocation, setRelocation] = useState(profile.relocation_allowed);
  const [stipend, setStipend] = useState(
    profile.minimum_stipend === null || profile.minimum_stipend === undefined
      ? ""
      : String(profile.minimum_stipend),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stipendValue = stipend.trim() === "" ? null : Number(stipend);
  const stipendValid = stipend.trim() === "" || (Number.isInteger(stipendValue) && (stipendValue ?? 0) >= 0);
  const dirty =
    experience.trim() !== (profile.experience_level ?? "") ||
    workMode.trim() !== (profile.preferred_work_mode ?? "") ||
    relocation !== profile.relocation_allowed ||
    (stipend.trim() === "" ? null : Number(stipend)) !== profile.minimum_stipend;

  async function save() {
    if (!stipendValid) {
      setError("Minimum stipend must be a whole number or empty.");
      return;
    }
    setBusy(true);
    setError(null);
    onSaveState({ kind: "saving", label: "Updating preferences…" });
    try {
      const next = await patchProfile(undefined, {
        experience_level: experience.trim() || null,
        preferred_work_mode: workMode.trim() || null,
        relocation_allowed: relocation,
        minimum_stipend: stipend.trim() === "" ? null : Number(stipend),
      });
      onSaved(next);
      onSaveState({ kind: "saved", label: "Preferences updated." });
    } catch {
      setError("Could not save. Check the API and try again.");
      onSaveState({ kind: "error", label: "Preferences save failed." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section
      title="Job preferences"
      blurb="How opportunities are matched and filtered for you."
      action={
        <button type="button" className={BTN_PRIMARY} disabled={busy || !dirty || !stipendValid} onClick={save}>
          {busy ? "Saving…" : "Save"}
        </button>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className={LABEL} htmlFor="profile-experience">
            Experience Level
          </label>
          <input
            id="profile-experience"
            className={INPUT}
            value={experience}
            disabled={busy}
            placeholder="Fresher / Student"
            onChange={(event) => setExperience(event.target.value)}
          />
        </div>
        <div>
          <label className={LABEL} htmlFor="profile-work-mode">
            Preferred Work Mode
          </label>
          <input
            id="profile-work-mode"
            className={INPUT}
            value={workMode}
            disabled={busy}
            placeholder="Remote + On-site"
            onChange={(event) => setWorkMode(event.target.value)}
          />
        </div>
        <div className="flex items-center gap-3 rounded-lg border border-line bg-ink-850 px-3 py-2">
          <input
            id="profile-relocation"
            type="checkbox"
            checked={relocation}
            disabled={busy}
            onChange={(event) => setRelocation(event.target.checked)}
            className="h-4 w-4 accent-[#7C6CFF]"
          />
          <label htmlFor="profile-relocation" className="text-sm text-zinc-200">
            Open to relocation
          </label>
        </div>
        <div>
          <label className={LABEL} htmlFor="profile-stipend">
            Minimum Stipend (optional)
          </label>
          <input
            id="profile-stipend"
            className={INPUT}
            value={stipend}
            disabled={busy}
            inputMode="numeric"
            placeholder="e.g. 15000"
            onChange={(event) => setStipend(event.target.value)}
          />
        </div>
      </div>
      <FieldError message={error} />
    </Section>
  );
}
