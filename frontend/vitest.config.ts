// Minimal Vitest setup (Phase 8): unit tests for pure logic + a small number
// of hook/context/component tests. No E2E, no browser automation.
import path from "path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: { alias: { "@": path.resolve(__dirname, ".") } },
  // Automatic JSX runtime (matches Next.js behavior) so component sources
  // need no React import shims for tests.
  esbuild: { jsx: "automatic" },
  test: {
    environment: "jsdom",
    include: ["lib/**/*.test.ts", "components/**/*.test.{ts,tsx}"],
  },
});
