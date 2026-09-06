import type { HTMLAttributes, TableHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Table({ className, containerProps, ...props }: TableHTMLAttributes<HTMLTableElement> & { containerProps?: HTMLAttributes<HTMLDivElement> }) {
  const { className: containerClassName, ...restContainerProps } = containerProps ?? {};
  return (
    <div className={cn("table-scroll", containerClassName)} {...restContainerProps}>
      <table className={cn("data-table", className)} {...props} />
    </div>
  );
}

export function TableHeader({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={className} {...props} />;
}

export function TableBody({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={className} {...props} />;
}

export function TableRow({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={className} {...props} />;
}

export function TableHead({ className, ...props }: HTMLAttributes<HTMLTableCellElement>) {
  return <th scope="col" className={className} {...props} />;
}

export function TableCell({ className, ...props }: HTMLAttributes<HTMLTableCellElement>) {
  return <td className={className} {...props} />;
}
