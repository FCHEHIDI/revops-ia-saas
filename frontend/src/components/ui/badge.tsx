import { type HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export type BadgeVariant = "success" | "warning" | "error" | "info" | "neutral";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const variantClasses: Record<BadgeVariant, string> = {
  success: "bg-emerald-900/50 text-emerald-400 border-emerald-800",
  warning: "bg-amber-900/50 text-amber-400 border-amber-800",
  error: "bg-red-dim/50 text-red border-red/30",
  info: "bg-blue-dim text-blue border-blue/30",
  neutral: "bg-elevated/50 text-text-secondary border-border-default",
};

export function Badge({ variant = "neutral", className, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
        variantClasses[variant],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
}
