import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { MetricDelta } from "@/components/evidence/metric-delta";

const meta = {
  title: "Comparison/Metric Delta",
  component: MetricDelta,
  parameters: { viewport: { defaultViewport: "mobile" } },
  argTypes: {
    direction: {
      control: { type: "select" },
      options: ["higher_is_better", "lower_is_better"],
    },
    status: {
      control: { type: "select" },
      options: ["PASS", "REGRESSION", "MISSING"],
    },
  },
  args: { delta: 0.05, direction: "lower_is_better", status: "REGRESSION" },
} satisfies Meta<typeof MetricDelta>;

export default meta;
type Story = StoryObj<typeof meta>;

export const LowerIsBetterRegression: Story = {};
