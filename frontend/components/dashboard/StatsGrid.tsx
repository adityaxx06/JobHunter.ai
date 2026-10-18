import { cn } from "@/lib/utils";

export function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="rounded-xl2 border border-line bg-ink-900 p-5 shadow-card">
      <p className="text-[13px] font-medium text-fog">{label}</p>
      <p className="mt-1.5 text-3xl font-semibold tabular-nums tracking-tight" aria-live="polite">
        {value}
      </p>
      <p className="mt-1 text-xs text-fog-dim">{hint}</p>
    </div>
  );
}

export function StatsGrid({ stats }: { stats: { label: string; value: string; hint: string }[] }) {
  return (
    <div
      className={cn(
        "grid grid-cols-1 gap-3",
        "min-[480px]:grid-cols-2",
        "lg:grid-cols-4",
      )}
    >
      {stats.map((stat) => (
        <StatCard key={stat.label} {...stat} />
      ))}
    </div>
  );
}
