"use client";

// Application shell: responsive sidebar + header + content.
// Desktop (lg+): fixed sidebar. Mobile: top bar with a slide-over menu.
import { useState } from "react";
import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { cn } from "@/lib/utils";

export function AppShell({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="min-h-screen bg-ink-950 text-zinc-100">
      {/* Mobile slide-over sidebar */}
      <div
        className={cn(
          "fixed inset-0 z-40 lg:hidden",
          menuOpen ? "pointer-events-auto" : "pointer-events-none",
        )}
        aria-hidden={!menuOpen}
      >
        <div
          className={cn(
            "absolute inset-0 bg-black/60 transition-opacity",
            menuOpen ? "opacity-100" : "opacity-0",
          )}
          onClick={() => setMenuOpen(false)}
        />
        <div
          className={cn(
            "absolute inset-y-0 left-0 w-72 max-w-[85vw] transition-transform duration-200",
            menuOpen ? "translate-x-0" : "-translate-x-full",
          )}
        >
          <Sidebar onNavigate={() => setMenuOpen(false)} />
        </div>
      </div>

      {/* Desktop sidebar */}
      <div className="fixed inset-y-0 left-0 z-30 hidden w-64 lg:block">
        <Sidebar />
      </div>

      <div className="lg:pl-64">
        <Header title={title} onMenu={() => setMenuOpen(true)} />
        <main className="mx-auto w-full max-w-6xl px-4 pb-16 pt-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
