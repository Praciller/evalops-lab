import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { MetricStat } from "@/components/evidence/metric-stat";

const meta = {
  title: "Patterns/Metric Stat",
  component: MetricStat,
  parameters: { viewport: { defaultViewport: "desktop" } },
  args: { label: "hit_rate_at_5", value: 0.75, context: "SYNTHETIC_FIXTURE · INTEGRATION_ONLY" },
} satisfies Meta<typeof MetricStat>;

export default meta;
type Story = StoryObj<typeof meta>;

export const SyntheticMetric: Story = {};
