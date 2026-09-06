import { ProductHeader } from "@/components/shell/product-header";

export function EvidenceLayout({ children }: { children: React.ReactNode }) {
  const storybookHref = process.env.GITHUB_PAGES === "true" ? "/evalops-lab/storybook/" : "/storybook/";

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <ProductHeader storybookHref={storybookHref} />
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
