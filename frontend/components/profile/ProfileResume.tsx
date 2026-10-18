// Resume Intelligence: upload -> parse -> review -> explicit approval.
// Parse-only backend: nothing here mutates the profile until the user
// checks items and clicks Apply. Merge semantics come free from the
// duplicate-safe CRUD endpoints (existing skills/roles are preserved).
"use client";

import { useRef, useState } from "react";
import { addRole, addSkill, parseResume, patchProfile } from "@/lib/api";
import type { ResumeExtraction } from "@/types/job";
import { BTN_DANGER, BTN_GHOST, BTN_PRIMARY, FieldError, Section } from "./common";
import type { SaveState } from "./ProfileSaveState";

const ACCEPTED = ".pdf,.docx,.txt";
const MAX_BYTES = 5 * 1024 * 1024;

type Phase = "idle" | "uploading" | "review" | "applying" | "done";

export function ProfileResume({ onProfileChanged }: { onProfileChanged: () => void }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [extraction, setExtraction] = useState<ResumeExtraction | null>(null);
  const [fileLabel, setFileLabel] = useState("");
  const [skills, setSkills] = useState<string[]>([]);
  const [roles, setRoles] = useState<string[]>([]);
  const [applyName, setApplyName] = useState(false);
  const [education, setEducation] = useState("");
  const [applyExperience, setApplyExperience] = useState(false);
  const [applied, setApplied] = useState<string[]>([]);
  const [saveState, setSaveState] = useState<SaveState>({ kind: "idle" });
  const inputRef = useRef<HTMLInputElement>(null);

  function toggle(list: string[], value: string, on: boolean, set: (next: string[]) => void) {
    set(on ? [...list, value] : list.filter((item) => item !== value));
  }

  async function upload(file: File) {
    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".pdf") && !lower.endsWith(".docx") && !lower.endsWith(".txt")) {
      setError("Unsupported file type. Upload a PDF, DOCX, or TXT resume.");
      return;
    }
    if (file.size <= 0) {
      setError("Empty file. Upload a resume with readable content.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("File too large. Resumes must be 5 MB or smaller.");
      return;
    }
    setPhase("uploading");
    setError(null);
    try {
      const response = await parseResume(file);
      if (!response.extraction) {
        setError(response.parse_error?.message ?? "Resume analysis failed. Try again.");
        setPhase("idle");
        return;
      }
      const next = response.extraction;
      setExtraction(next);
      setFileLabel(file.name);
      setSkills(next.skills.map((skill) => skill.name));
      setRoles(next.target_roles);
      setApplyName(Boolean(next.full_name));
      setEducation(next.education[0] ?? "");
      setApplyExperience(Boolean(next.experience_level));
      setApplied([]);
      setPhase("review");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed. Try again.");
      setPhase("idle");
    }
  }

  async function apply() {
    if (!extraction) return;
    setPhase("applying");
    setError(null);
    const done: string[] = [];
    try {
      if (applyName && extraction.full_name) {
        await patchProfile(undefined, { full_name: extraction.full_name });
        done.push("name");
      }
      if (education) {
        await patchProfile(undefined, { education });
        done.push("education");
      }
      if (applyExperience && extraction.experience_level) {
        await patchProfile(undefined, { experience_level: extraction.experience_level });
        done.push("experience level");
      }
      for (const name of skills) {
        await addSkill(undefined, { skill_name: name });
        done.push(`skill ${name}`);
      }
      for (const role of roles) {
        await addRole(undefined, { role_name: role });
        done.push(`role ${role}`);
      }
      setApplied(done);
      setSaveState({ kind: "saved", label: "Resume changes applied." });
      setPhase("done");
      onProfileChanged();
    } catch {
      setError(
        done.length === 0
          ? "Could not apply changes. Nothing was changed."
          : `Stopped after applying ${done.length} change(s). Already applied items were kept; retry the rest.`,
      );
      setSaveState({ kind: "error", label: "Apply incomplete." });
      setPhase("review");
    }
  }

  function reset() {
    setPhase("idle");
    setError(null);
    setExtraction(null);
    setApplied([]);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <Section
      title="Resume"
      blurb="Upload a resume to detect skills and roles. Nothing changes until you review and apply."
      action={
        saveState.kind !== "idle" ? (
          <span className="text-sm text-positive" role="status">
            {saveState.label}
          </span>
        ) : undefined
      }
    >
      {phase === "idle" && (
        <div>
          <label
            htmlFor="resume-file"
            className="block cursor-pointer rounded-lg border border-dashed border-line bg-ink-850 px-4 py-6 text-center text-sm text-fog transition-colors hover:border-accent/50 hover:text-zinc-200"
          >
            Choose PDF / DOCX / TXT (max 5 MB)
            <input
              id="resume-file"
              ref={inputRef}
              type="file"
              accept={ACCEPTED}
              className="sr-only"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) upload(file);
              }}
            />
          </label>
          <p className="mt-2 text-xs text-fog-faint">
            Supported formats: PDF, DOCX, TXT. The file is processed in memory and discarded — it is
            never stored.
          </p>
          <FieldError message={error} />
        </div>
      )}

      {phase === "uploading" && (
        <p className="text-sm text-caution" role="status">
          Analyzing resume… this calls the AI parser once.
        </p>
      )}

      {(phase === "review" || phase === "applying") && extraction && (
        <div className="space-y-4">
          <p className="truncate text-xs text-fog-faint" title={fileLabel}>
            Source file: {fileLabel} — review everything before applying. Existing preferences stay
            untouched.
          </p>

          {extraction.full_name && (
            <label className="flex items-center gap-3 rounded-lg border border-line-soft bg-ink-850 px-3 py-2">
              <input
                type="checkbox"
                checked={applyName}
                disabled={phase === "applying"}
                onChange={(event) => setApplyName(event.target.checked)}
                className="h-4 w-4 accent-[#7C6CFF]"
              />
              <span className="text-sm text-zinc-200">
                Detected name: <strong>{extraction.full_name}</strong>
              </span>
            </label>
          )}

          {extraction.education.length > 0 && (
            <fieldset>
              <legend className="mb-1 text-xs font-medium uppercase tracking-wide text-fog">
                Detected education (pick one, or none)
              </legend>
              <div className="space-y-1.5">
                <label className="flex items-center gap-3 rounded-lg border border-line-soft bg-ink-850 px-3 py-2">
                  <input
                    type="radio"
                    name="resume-education"
                    checked={education === ""}
                    disabled={phase === "applying"}
                    onChange={() => setEducation("")}
                    className="h-4 w-4 accent-[#7C6CFF]"
                  />
                  <span className="text-sm text-fog">Keep current education</span>
                </label>
                {extraction.education.map((item) => (
                  <label
                    key={item}
                    className="flex items-center gap-3 rounded-lg border border-line-soft bg-ink-850 px-3 py-2"
                  >
                    <input
                      type="radio"
                      name="resume-education"
                      checked={education === item}
                      disabled={phase === "applying"}
                      onChange={() => setEducation(item)}
                      className="h-4 w-4 accent-[#7C6CFF]"
                    />
                    <span className="text-sm text-zinc-200">{item}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}

          {extraction.experience_level && (
            <label className="flex items-center gap-3 rounded-lg border border-line-soft bg-ink-850 px-3 py-2">
              <input
                type="checkbox"
                checked={applyExperience}
                disabled={phase === "applying"}
                onChange={(event) => setApplyExperience(event.target.checked)}
                className="h-4 w-4 accent-[#7C6CFF]"
              />
              <span className="text-sm text-zinc-200">
                Detected experience: <strong>{extraction.experience_level}</strong>
              </span>
            </label>
          )}

          {extraction.skills.length > 0 && (
            <fieldset>
              <legend className="mb-1 text-xs font-medium uppercase tracking-wide text-fog">
                Detected skills ({skills.length} selected)
              </legend>
              <ul className="grid gap-1.5 sm:grid-cols-2">
                {extraction.skills.map((skill) => (
                  <li key={skill.name}>
                    <label className="flex items-center gap-2.5 rounded-lg border border-line-soft bg-ink-850 px-3 py-2">
                      <input
                        type="checkbox"
                        checked={skills.includes(skill.name)}
                        disabled={phase === "applying"}
                        onChange={(event) => toggle(skills, skill.name, event.target.checked, setSkills)}
                        className="h-4 w-4 accent-[#7C6CFF]"
                      />
                      <span className="truncate text-sm text-zinc-200">{skill.name}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </fieldset>
          )}

          {extraction.target_roles.length > 0 && (
            <fieldset>
              <legend className="mb-1 text-xs font-medium uppercase tracking-wide text-fog">
                Suggested roles ({roles.length} selected — suggestions only, existing roles kept)
              </legend>
              <ul className="grid gap-1.5 sm:grid-cols-2">
                {extraction.target_roles.map((role) => (
                  <li key={role}>
                    <label className="flex items-center gap-2.5 rounded-lg border border-line-soft bg-ink-850 px-3 py-2">
                      <input
                        type="checkbox"
                        checked={roles.includes(role)}
                        disabled={phase === "applying"}
                        onChange={(event) => toggle(roles, role, event.target.checked, setRoles)}
                        className="h-4 w-4 accent-[#7C6CFF]"
                      />
                      <span className="truncate text-sm text-zinc-200">{role}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </fieldset>
          )}

          {(extraction.email || extraction.phone) && (
            <p className="text-xs text-fog-faint">
              Contact details detected but never saved to your profile:
              {[extraction.email, extraction.phone].filter(Boolean).join(" · ")}
            </p>
          )}

          <FieldError message={error} />
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={BTN_PRIMARY}
              disabled={phase === "applying"}
              onClick={apply}
            >
              {phase === "applying" ? "Applying…" : "Apply selected changes"}
            </button>
            <button type="button" className={BTN_GHOST} disabled={phase === "applying"} onClick={reset}>
              Discard
            </button>
          </div>
        </div>
      )}

      {phase === "done" && (
        <div>
          <p className="text-sm text-positive" role="status">
            Applied {applied.length} change(s). Existing skills and roles were preserved.
          </p>
          <button type="button" className={BTN_DANGER} onClick={reset}>
            Analyze another resume
          </button>
        </div>
      )}
    </Section>
  );
}
