import Link from "next/link";

import { PrimaryNav } from "@/components/shell/primary-nav";
import { ThemeToggle } from "@/components/theme-toggle";

export function ProductHeader({ storybookHref }: { storybookHref: string }) {
  return (
    <header className="border-b border-line bg-surface/90">
      <div className="page-shell flex flex-wrap items-center gap-x-6 gap-y-3 py-4">
        <Link className="focus-ring shrink-0 rounded-md" href="/">
          <span className="block text-xs font-bold uppercase tracking-[0.16em] text-accent">
            EvalOps Lab
          </span>
          <span className="block text-sm font-semibold text-ink">Evidence Console</span>
        </Link>
        <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-3">
          <PrimaryNav storybookHref={storybookHref} />
          <span className="hidden whitespace-nowrap text-xs text-muted xl:inline">Static · read-only</span>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
