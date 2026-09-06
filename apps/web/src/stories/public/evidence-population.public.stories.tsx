import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { PopulationCompatibilityBadge } from "@/components/evidence/population-compatibility-badge";

const meta = {
  title: "Evidence/Population Compatibility",
  component: PopulationCompatibilityBadge,
  argTypes: {
    status: {
      control: { type: "select" },
      options: ["MATCHED", "UNVERIFIED", "INCOMPATIBLE"],
    },
  },
  args: { status: "MATCHED" },
} satisfies Meta<typeof PopulationCompatibilityBadge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const AllStates: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      <PopulationCompatibilityBadge status="MATCHED" />
      <PopulationCompatibilityBadge status="UNVERIFIED" />
      <PopulationCompatibilityBadge status="INCOMPATIBLE" />
    </div>
  ),
};
