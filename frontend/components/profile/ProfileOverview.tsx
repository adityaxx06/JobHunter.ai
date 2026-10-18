// Identity fields: full name + education (existing scalar columns only).
import { useState } from "react";
import { patchProfile } from "@/lib/api";
import type { ProfileScalar } from "@/types/job";
import { BTN_PRIMARY, FieldError, INPUT, LABEL, Section } from "./common";
import type { SaveState } from "./ProfileSaveState";

export function ProfileOverview({
  profile,
  onSaved,
  onSaveState,
}: {
  profile: ProfileScalar;
  onSaved: (next: ProfileScalar) => void;
  onSaveState: (state: SaveState) => void;
}) {
  const [fullName, setFullName] = useState(profile.full_name ?? "");
  const [education, setEducation] = useState(profile.education ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty =
    fullName.trim() !== (profile.full_name ?? "") || education.trim() !== (profile.education ?? "");

  async function save() {
    setBusy(true);
    setError(null);
    onSaveState({ kind: "saving", label: "Updating profile…" });
    try {
      const next = await patchProfile(undefined, {
        full_name: fullName.trim() || null,
        education: education.trim() || null,
      });
      onSaved(next);
      onSaveState({ kind: "saved", label: "Profile updated." });
    } catch {
      setError("Could not save. Check the API and try again.");
      onSaveState({ kind: "error", label: "Profile save failed." });
    } finally {
      setBusy(false);
    }
  }

  void dirty;
  return (
    <Section
      title="Profile"
      blurb="Your identity as stored on the candidate profile."
      action={
        <button type="button" className={BTN_PRIMARY} disabled={busy || !dirty} onClick={save}>
          {busy ? "Saving…" : "Save"}
        </button>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className={LABEL} htmlFor="profile-full-name">
            Full Name
          </label>
          <input
            id="profile-full-name"
            className={INPUT}
            value={fullName}
            disabled={busy}
            placeholder="Dev Candidate"
            onChange={(event) => setFullName(event.target.value)}
          />
        </div>
        <div>
          <label className={LABEL} htmlFor="profile-education">
            Education
          </label>
          <input
            id="profile-education"
            className={INPUT}
            value={education}
            disabled={busy}
            placeholder="MCA"
            onChange={(event) => setEducation(event.target.value)}
          />
        </div>
      </div>
      <FieldError message={error} />
    </Section>
  );
}
