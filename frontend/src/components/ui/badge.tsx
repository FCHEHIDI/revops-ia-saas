import { type CSSProperties, type HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export type BadgeVariant = "success" | "warning" | "error" | "info" | "neutral";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const variantStyles: Record<BadgeVariant, CSSProperties> = {
  success: { background: "rgba(77,255,145,0.10)", color: "#4dff91",  border: "1px solid rgba(77,255,145,0.25)" },
  warning: { background: "rgba(255,153,0,0.10)",  color: "#FF9900",  border: "1px solid rgba(255,153,0,0.25)"  },
  error:   { background: "rgba(192,0,0,0.10)",    color: "var(--red-glow)", border: "1px solid rgba(192,0,0,0.30)" },
  info:    { background: "rgba(41,121,255,0.10)", color: "#2979FF",  border: "1px solid rgba(41,121,255,0.25)" },
  neutral: { background: "rgba(85,85,85,0.12)",   color: "var(--text-secondary)", border: "1px solid var(--border-default)" },
};

export function Badge({ variant = "neutral", className, style, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        className
      )}
      style={{ ...variantStyles[variant], ...style }}
      {...props}
    >
      {children}
    </span>
  );
}

