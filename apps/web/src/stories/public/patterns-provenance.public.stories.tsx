import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Card } from "@/components/ui/card";

const meta = { title: "Patterns/Provenance", component: Card } satisfies Meta<typeof Card>;

export default meta;
type Story = StoryObj<typeof meta>;

export const SyntheticFixture: Story = {
  render: () => (
    <Card className="max-w-xl p-5">
      <p className="eyebrow">Public evidence boundary</p>
      <h2 className="section-title">demo-retrieval-fixture-v1</h2>
      <div className="mt-4 flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-[0.08em]">
        <span className="badge-data-synthetic rounded-full border px-2 py-1">SYNTHETIC_FIXTURE</span>
        <span className="badge-scope rounded-full border px-2 py-1">INTEGRATION_ONLY</span>
      </div>
      <p className="mt-4 text-sm leading-6 text-ink-muted">A safe fixture demonstrates the inspection vocabulary without making a benchmark claim.</p>
    </Card>
  ),
};
