import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const meta = { title: "Primitives/Table" } satisfies Meta<typeof Table>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Metric</TableHead>
          <TableHead>Value</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow>
          <TableCell>Hit rate at 5</TableCell>
          <TableCell className="technical">0.750</TableCell>
        </TableRow>
      </TableBody>
    </Table>
  ),
};
