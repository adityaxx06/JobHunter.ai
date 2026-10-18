import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// shadcn/ui helper (Phase 1 — ready for future components, no UI built yet).
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
