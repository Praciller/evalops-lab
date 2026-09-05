import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Card } from "@/components/ui/card";

const meta = { title: "Primitives/Card", component: Card } satisfies Meta<typeof Card>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <Card className="max-w-md p-5">
      <h2 className="text-base font-semibold text-ink">A restrained surface</h2>
      <p className="mt-2 text-sm text-ink-muted">Cards support hierarchy without turning every field into decoration.</p>
    </Card>
  ),
};
