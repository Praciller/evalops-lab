import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Card } from "@/components/ui/card";

const meta = {
  title: "Foundations/Canvas",
  component: Card,
  parameters: { layout: "centered", viewport: { defaultViewport: "desktop" } },
} satisfies Meta<typeof Card>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Light: Story = {
  args: {
    children: (
      <div>
        <p className="eyebrow">Evidence over decoration</p>
        <h1 className="section-title">Evidence Console</h1>
        <p className="mt-2 text-sm text-ink-muted">Neutral surfaces, semantic tokens, and inspectable evidence.</p>
      </div>
    ),
  },
};
