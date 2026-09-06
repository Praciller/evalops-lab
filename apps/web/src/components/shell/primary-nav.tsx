"use client";

import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const appRoutes = [
  { href: "/", label: "Overview" },
  { href: "/runs/", label: "Runs" },
  { href: "/comparisons/", label: "Comparisons" },
] as const;

const appBasePath = process.env.GITHUB_PAGES === "true" ? "/evalops-lab" : "";

export function PrimaryNav({ storybookHref }: { storybookHref: string }) {
  const pathname = usePathname() ?? "/";
  const routePathname = appBasePath && pathname.startsWith(appBasePath) ? pathname.slice(appBasePath.length) || "/" : pathname;

  return (
    <nav aria-label="Primary navigation" className="flex max-w-full flex-wrap items-center gap-1">
      {appRoutes.map((route) => {
        const active = route.href === "/" ? routePathname === "/" : routePathname.startsWith(route.href);
        return (
          <a
            className={cn(
              "focus-ring rounded-md px-2.5 py-1.5 text-sm font-semibold transition-colors",
              active ? "bg-accent-soft text-accent" : "text-muted hover:bg-canvas hover:text-ink",
            )}
            href={`${appBasePath}${route.href}`}
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
