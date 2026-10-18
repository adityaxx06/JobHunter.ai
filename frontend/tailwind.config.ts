import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#0A0A0B", // app background
          900: "#111113", // surface
          850: "#161619", // raised surface
          800: "#18181B", // elevated surface
          700: "#232326", // borders on dark fills
        },
        line: {
          DEFAULT: "#232327", // subtle neutral border
          soft: "#1B1B1F",
        },
        accent: {
          DEFAULT: "#7C6CFF", // single restrained accent (violet)
          soft: "#A99CFF",
          dim: "rgba(124, 108, 255, 0.12)",
        },
        positive: "#34D399",
        caution: "#FBBF24",
        danger: "#F87171",
        fog: {
          DEFAULT: "#A1A1AA", // muted text
          dim: "#71717A",
          faint: "#52525B",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      boxShadow: {
        card: "0 1px 2px rgba(0, 0, 0, 0.4), 0 8px 24px -12px rgba(0, 0, 0, 0.5)",
        pop: "0 12px 32px -12px rgba(0, 0, 0, 0.65)",
      },
      borderRadius: {
        xl2: "0.875rem",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "-400px 0" },
          "100%": { backgroundPosition: "400px 0" },
        },
        rise: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        shimmer: "shimmer 1.6s linear infinite",
        rise: "rise 0.35s ease-out both",
      },
    },
  },
  plugins: [],
};

export default config;
