import type { Preview } from "@storybook/nextjs-vite";
import type { ReactNode } from "react";

import "../src/app/globals.css";

const preview: Preview = {
  parameters: {
    a11y: { test: "error" },
    controls: { expanded: true },
    layout: "padded",
    viewport: {
      viewports: {
        mobile: { name: "Mobile", styles: { height: "844px", width: "390px" } },
        tablet: { name: "Tablet", styles: { height: "1024px", width: "768px" } },
        desktop: { name: "Desktop", styles: { height: "900px", width: "1440px" } },
      },
    },
  },
  globalTypes: {
    colorScheme: {
      description: "Evidence Console theme",
      defaultValue: "light",
      toolbar: {
        icon: "paintbrush",
        items: ["light", "dark"],
      },
    },
  },
  decorators: [
    (Story, context) => {
      const colorScheme = context.globals.colorScheme === "dark" ? "dark" : "light";
      return (
        <main className={`${colorScheme} min-h-screen bg-canvas p-4 text-ink`}>
          <Story />
        </main>
      ) as ReactNode;
    },
  ],
};

export default preview;
