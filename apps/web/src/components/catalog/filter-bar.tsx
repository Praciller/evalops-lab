import { humanizeLabel } from "@/lib/evidence/format";
import type { FilterKey } from "@/lib/evidence/filters";

export type FilterOption = {
  key: FilterKey;
  label: string;
  values: readonly string[];
};

export function FilterBar({
  options,
  active,
  onChange,
  onClear,
  onClearAll,
}: {
  options: readonly FilterOption[];
  active: Partial<Record<FilterKey, string>>;
  onChange: (key: FilterKey, value: string | null) => void;
  onClear: (key: FilterKey) => void;
  onClearAll: () => void;
}) {
  const activeEntries = options.filter(({ key }) => active[key]);

  return (
    <section className="surface p-4" aria-label="Evidence filters">
      <div className="flex flex-wrap items-end gap-3">
        {options.map((option) => (
          <label className="grid min-w-[10rem] flex-1 gap-1.5 text-xs font-semibold text-muted" htmlFor={`filter-${option.key}`} key={option.key}>
            {option.label}
            <select
              aria-label={option.label}
              className="control focus-ring w-full"
              id={`filter-${option.key}`}
              value={active[option.key] ?? ""}
              onChange={(event) => onChange(option.key, event.target.value || null)}
            >
              <option value="">All</option>
              {option.values.map((value) => (
                <option key={value} value={value}>
                  {humanizeLabel(value)}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted" aria-live="polite">
        <span>{activeEntries.length ? "Active filters:" : "No filters selected"}</span>
        {activeEntries.map(({ key, label }) => (
          <button aria-label={`Clear ${label} filter`} className="focus-ring rounded-md px-2 py-1 text-accent underline underline-offset-2" key={key} type="button" onClick={() => onClear(key)}>
            {label}: {humanizeLabel(active[key] ?? "")} · clear
          </button>
        ))}
        {activeEntries.length ? (
          <button className="control focus-ring ml-auto" type="button" onClick={onClearAll}>
            Clear all filters
          </button>
        ) : null}
      </div>
    </section>
  );
}
