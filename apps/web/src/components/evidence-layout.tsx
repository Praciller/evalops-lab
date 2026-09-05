import Link from "next/link";

import { ThemeToggle } from "@/components/theme-toggle";

export function EvidenceLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="border-b border-line bg-surface/90">
        <div className="page-shell flex items-center justify-between gap-4 py-4">
          <Link className="focus-ring rounded-md" href="/">
            <span className="block text-xs font-bold uppercase tracking-[0.16em] text-accent">
              EvalOps Lab
            </span>
            <span className="block text-sm font-semibold text-ink">Evidence Console</span>
          </Link>
          <div className="flex items-center gap-3">
            <span className="hidden text-xs text-muted sm:inline">Static · read-only</span>
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className="page-shell py-8 sm:py-12">{children}</main>
      <footer className="border-t border-line">
        <div className="page-shell flex flex-col gap-2 py-6 text-xs text-muted sm:flex-row sm:items-center sm:justify-between">
          <span>Public Evidence Contract V1 · explicit allowlist</span>
          <span className="font-mono">No runtime API · no inference · no raw corpus</span>
        </div>
      </footer>
    </div>
  );
}

export function ErrorState() {
  return (
    <section className="surface border-danger/40 p-6" role="alert" aria-labelledby="evidence-error">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-danger">Unavailable</p>
      <h1 id="evidence-error" className="mt-2 text-2xl font-semibold text-ink">
        Evidence unavailable
      </h1>
      <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
        This public artifact could not be validated. No raw JSON, local paths, or internal diagnostics are shown.
      </p>
    </section>
  );
}
