"use client";

import { useEffect, useState } from "react";

export function ThemeToggle() {
  const [dark, setDark] = useState<boolean | null>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem("evalops-theme");
    const prefersDark = typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const nextDark = stored ? stored === "dark" : prefersDark;
    document.documentElement.classList.toggle("dark", nextDark);
    // The browser preference is external state; update the label after hydration.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDark(nextDark);
  }, []);

  function toggleTheme() {
    const nextDark = !dark;
    document.documentElement.classList.toggle("dark", nextDark);
    window.localStorage.setItem("evalops-theme", nextDark ? "dark" : "light");
    setDark(nextDark);
  }

  return (
    <button className="control focus-ring" type="button" onClick={toggleTheme}>
      <span aria-hidden="true">{dark ? "☼" : "◐"}</span>
      <span>{dark === null ? "Theme" : `${dark ? "Light" : "Dark"} theme`}</span>
    </button>
  );
}
