import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { ClaimScopeBadge, DataKindBadge, VerificationBadge } from "@/components/evidence/evidence-badges";

const meta = {
  title: "Evidence/Claim Badges",
  component: VerificationBadge,
  parameters: { viewport: { defaultViewport: "tablet" } },
  argTypes: {
    status: {
      control: { type: "select" },
      options: ["VERIFIED", "PARTIAL", "UNVERIFIED", "NOT_RUN"],
    },
  },
  args: { status: "VERIFIED" },
} satisfies Meta<typeof VerificationBadge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const AllClaimDimensions: Story = {
  render: () => (
    <div className="flex max-w-xl flex-wrap gap-2">
      <VerificationBadge status="VERIFIED" />
      <DataKindBadge dataKind="SYNTHETIC_FIXTURE" />
      <ClaimScopeBadge scope="INTEGRATION_ONLY" />
    </div>
  ),
};
