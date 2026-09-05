import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { EmptyState } from "@/components/evidence/empty-state";

const meta = {
  title: "Evidence/Empty States",
  component: EmptyState,
  argTypes: {
    kind: {
      control: { type: "select" },
      options: ["no_artifacts", "no_results", "comparison_unavailable", "unsupported", "invalid_artifact"],
    },
  },
  args: { kind: "comparison_unavailable" },
} satisfies Meta<typeof EmptyState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ComparisonUnavailable: Story = {};
