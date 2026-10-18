// /profile — candidate profile workspace. One bundle fetch (profile +
// skills + roles + locations); every section mutates through the profile
// API and refreshes local state. Read-only until the bundle loads; every
// failure surfaces inline with a retry — never a fake number.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { DashboardError } from "@/components/dashboard/DashboardError";
import { ProfileLocations } from "@/components/profile/ProfileLocations";
import { ProfileOverview } from "@/components/profile/ProfileOverview";
import { ProfilePreferences } from "@/components/profile/ProfilePreferences";
import { ProfileResume } from "@/components/profile/ProfileResume";
import { ProfileRoles } from "@/components/profile/ProfileRoles";
import { ProfileSaveState, IDLE_SAVE, type SaveState } from "@/components/profile/ProfileSaveState";
import { ProfileSkills } from "@/components/profile/ProfileSkills";
import { getProfile } from "@/lib/api";
import { DEFAULT_PROFILE_ID } from "@/lib/config";
import type { ProfileLocation, ProfileRole, ProfileScalar, ProfileSkill } from "@/types/job";

type PageStatus = "loading" | "ready" | "error";

export default function ProfilePage() {
  const [status, setStatus] = useState<PageStatus>("loading");
  const [profile, setProfile] = useState<ProfileScalar | null>(null);
  const [skills, setSkills] = useState<ProfileSkill[]>([]);
  const [roles, setRoles] = useState<ProfileRole[]>([]);
  const [locations, setLocations] = useState<ProfileLocation[]>([]);
  const [saveState, setSaveState] = useState<SaveState>(IDLE_SAVE);
  const requestId = useRef(0);

  const load = useCallback(() => {
    const current = ++requestId.current;
    setStatus("loading");
    getProfile(DEFAULT_PROFILE_ID)
      .then((response) => {
        if (current !== requestId.current) return;
        setProfile(response.profile);
        setSkills(response.skills);
        setRoles(response.target_roles);
        setLocations(response.target_locations);
        setStatus("ready");
      })
      .catch(() => {
        if (current !== requestId.current) return;
        setStatus("error");
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (status === "loading") {
    return (
      <AppShell title="Profile">
        <p className="text-sm text-fog" role="status">
          Loading your profile…
        </p>
      </AppShell>
    );
  }

  if (status === "error" || profile === null) {
    return (
      <AppShell title="Profile">
        <DashboardError onRetry={load} />
      </AppShell>
    );
  }

  return (
    <AppShell title="Profile">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-fog">
          Everything discovery, matching, and ranking know about you. Changes apply to future runs.
        </p>
        <ProfileSaveState state={saveState} />
      </div>
      <div className="space-y-4">
        <ProfileOverview profile={profile} onSaved={setProfile} onSaveState={setSaveState} />
        <ProfileResume onProfileChanged={load} />
        <ProfilePreferences profile={profile} onSaved={setProfile} onSaveState={setSaveState} />
        <ProfileSkills skills={skills} onChanged={setSkills} onSaveState={setSaveState} />
        <ProfileRoles roles={roles} onChanged={setRoles} onSaveState={setSaveState} />
        <ProfileLocations locations={locations} onChanged={setLocations} onSaveState={setSaveState} />
      </div>
    </AppShell>
  );
}
