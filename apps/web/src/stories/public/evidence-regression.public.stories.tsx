import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { RegressionIndicator } from "@/components/evidence/regression-indicator";

const meta = {
  title: "Evidence/Regression",
  component: RegressionIndicator,
  argTypes: {
    status: {
      control: { type: "select" },
      options: ["PASS", "REGRESSION", "MISSING"],
    },
  },
  args: { status: "REGRESSION" },
} satisfies Meta<typeof RegressionIndicator>;

export default meta;
type Story = StoryObj<typeof meta>;

export const AllStates: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      <RegressionIndicator status="PASS" />
      <RegressionIndicator status="REGRESSION" />
      <RegressionIndicator status="MISSING" />
    </div>
  ),
};
