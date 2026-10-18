import type { Metadata } from "next";
import { ApplicationStatusProvider } from "@/components/applications/ApplicationStatusContext";
import { SavedJobsProvider } from "@/components/saved/SavedJobsContext";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "AI-JobHunter — Personal Job Intelligence",
    template: "%s · AI-JobHunter",
  },
  description:
    "AI-evaluated internships and entry-level roles, ranked by match and trust.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body>
        <SavedJobsProvider>
          <ApplicationStatusProvider>{children}</ApplicationStatusProvider>
        </SavedJobsProvider>
      </body>
    </html>
  );
}
