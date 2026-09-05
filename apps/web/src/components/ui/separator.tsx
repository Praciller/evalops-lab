import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Separator({ className, ...props }: HTMLAttributes<HTMLHRElement>) {
  return <hr role="separator" className={cn("border-0 border-t border-line", className)} {...props} />;
}
