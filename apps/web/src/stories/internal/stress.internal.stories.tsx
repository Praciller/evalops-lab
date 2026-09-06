import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { EmptyState } from "@/components/evidence/empty-state";

const meta = {
  title: "Internal/Stress/Unavailable Evidence",
  component: EmptyState,
  args: { kind: "unsupported" },
} satisfies Meta<typeof EmptyState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const SafeFallback: Story = {};
