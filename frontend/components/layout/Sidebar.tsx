"use client";

// Primary navigation. Dashboard, Jobs, Applications, and Profile resolve;
// Saved and Settings remain intentionally non-interactive placeholders
// (aria-disabled, "Soon" badge) so no link can ever be broken.
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ApplicationsIcon,
  BookmarkIcon,
  BriefcaseIcon,
  DashboardIcon,
  SettingsIcon,
  SparkIcon,
  UserIcon,
} from "@/components/ui/icons";
import { cn } from "@/lib/utils";

interface NavEntry {
  label: string;
  href?: string;
  icon: (props: { size?: number }) => React.JSX.Element;
}

const NAV: NavEntry[] = [
  { label: "Dashboard", href: "/dashboard", icon: DashboardIcon },
  { label: "Jobs", href: "/jobs", icon: BriefcaseIcon },
  { label: "Saved", icon: BookmarkIcon },
  { label: "Applications", href: "/applications", icon: ApplicationsIcon },
  { label: "Profile", href: "/profile", icon: UserIcon },
  { label: "Settings", icon: SettingsIcon },
];

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-full flex-col border-r border-line bg-ink-900">
      <div className="flex items-center gap-2.5 px-5 pb-5 pt-6">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-dim text-accent-soft">
          <SparkIcon size={20} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-[15px] font-semibold tracking-tight">AI-JobHunter</p>
          <p className="truncate text-xs text-fog">Personal Job Intelligence</p>
        </div>
      </div>

      <nav aria-label="Primary" className="flex-1 space-y-1 overflow-y-auto px-3">
        {NAV.map((entry) => {
          const Icon = entry.icon;
          // Nested routes (e.g. /jobs/[jobId]) keep their section highlighted.
          const active =
            entry.href !== undefined &&
            (pathname === entry.href || pathname.startsWith(`${entry.href}/`));
          if (!entry.href) {
            return (
              <span
                key={entry.label}
                aria-disabled="true"
                title="Coming soon"
                className="group flex cursor-not-allowed items-center gap-3 rounded-lg px-3 py-2 text-sm text-fog-dim"
              >
                <Icon size={18} />
                <span className="flex-1">{entry.label}</span>
                <span className="rounded-full border border-line px-1.5 py-px text-[10px] font-medium uppercase tracking-wide text-fog-faint">
                  Soon
                </span>
              </span>
            );
          }
          return (
            <Link
              key={entry.label}
              href={entry.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                "hover:bg-ink-800 hover:text-zinc-100",
                active
                  ? "bg-accent-dim font-medium text-zinc-50"
                  : "text-fog",
              )}
            >
              <Icon size={18} />
              {entry.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-line-soft p-4">
        <div className="flex items-center gap-3 rounded-lg px-1 py-1">
          <span
            aria-hidden="true"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink-800 text-sm font-semibold text-accent-soft"
          >
            A
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">Aditya</p>
            <p className="truncate text-xs text-fog">MCA Student</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
