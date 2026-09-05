import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.08em]",
        className,
      )}
      {...props}
    />
  );
}
