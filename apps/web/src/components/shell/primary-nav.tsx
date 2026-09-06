"use client";

import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const appRoutes = [
  { href: "/", label: "Overview" },
  { href: "/runs/", label: "Runs" },
  { href: "/comparisons/", label: "Comparisons" },
] as const;

export function PrimaryNav({ storybookHref }: { storybookHref: string }) {
  const pathname = usePathname() ?? "/";

  return (
    <nav aria-label="Primary navigation" className="flex max-w-full flex-wrap items-center gap-1">
      {appRoutes.map((route) => {
        const active = route.href === "/" ? pathname === "/" : pathname.startsWith(route.href);
        return (
          <a
            className={cn(
              "focus-ring rounded-md px-2.5 py-1.5 text-sm font-semibold transition-colors",
              active ? "bg-accent-soft text-accent" : "text-muted hover:bg-canvas hover:text-ink",
            )}
            href={route.href}
            aria-current={active ? "page" : undefined}
            key={route.href}
          >
            {route.label}
          </a>
        );
      })}
      <a
        className="focus-ring rounded-md px-2.5 py-1.5 text-sm font-semibold text-muted transition-colors hover:bg-canvas hover:text-ink"
        href={storybookHref}
      >
        Storybook
      </a>
    </nav>
  );
}
