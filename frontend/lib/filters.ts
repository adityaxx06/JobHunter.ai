// Centralized explorer filter/sort options (Phase 5.5C). Single place only —
// no role/location list is duplicated across components. Role and location
// options prefer the profile endpoint at runtime (see JobExplorer) and fall
// back to these presentation lists, which mirror the seeded profile.

export interface OptionItem {
  value: string;
  label: string;
}

export const ROLE_OPTIONS: string[] = [
  "Software Developer",
  "Software Engineer",
  "Java Developer",
  "Backend Developer",
  "Backend Engineer",
  "Full Stack Developer",
  "Web Developer",
  "Python Developer",
  "AI/ML Intern",
  "AI Engineer Intern",
  "Machine Learning Intern",
];

export const LOCATION_OPTIONS: string[] = [
  "India",
  "Chennai",
  "Bangalore",
  "Hyderabad",
  "Pune",
  "Mumbai",
  "Delhi NCR",
  "Gurgaon",
  "Noida",
  "Kolkata",
  "Remote",
];

export const REMOTE_OPTIONS: OptionItem[] = [
  { value: "all", label: "All" },
  { value: "remote", label: "Remote" },
  { value: "not-remote", label: "Not remote" },
];

export const MATCH_OPTIONS: OptionItem[] = [
  { value: "", label: "All" },
  { value: "90", label: "90+ Excellent" },
  { value: "80", label: "80+ Strong" },
  { value: "70", label: "70+ Good" },
  { value: "60", label: "60+ Maybe" },
];

export const TRUST_OPTIONS: OptionItem[] = [
  { value: "", label: "All" },
  { value: "90", label: "90+ High Trust" },
  { value: "80", label: "80+ Trusted" },
  { value: "70", label: "70+ Moderate+" },
];

export const RECOMMENDATION_OPTIONS: OptionItem[] = [
  { value: "", label: "All" },
  { value: "APPLY", label: "APPLY" },
  { value: "REVIEW", label: "REVIEW" },
  { value: "AVOID", label: "AVOID" },
];

export const EMPLOYMENT_OPTIONS: OptionItem[] = [
  { value: "", label: "All" },
  { value: "Internship", label: "Internship" },
  { value: "Full-time", label: "Full-time" },
  { value: "Part-time", label: "Part-time" },
  { value: "Contract", label: "Contract" },
];

export const SORT_OPTIONS: { value: "match" | "trust" | "newest"; label: string }[] = [
  { value: "match", label: "Best Match" },
  { value: "trust", label: "Highest Trust" },
  { value: "newest", label: "Newest" },
];

export const EXPLORER_PAGE_SIZE = 20;
