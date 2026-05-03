import { type HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  width?: string | number;
  height?: string | number;
  rounded?: "sm" | "md" | "lg" | "full";
}

const radiusMap = {
  sm:   "var(--radius-sm)",
  md:   "var(--radius-md)",
  lg:   "var(--radius-lg)",
  full: "9999px",
};

export function Skeleton({
  width,
  height,
  rounded = "md",
  className,
  style,
  ...props
}: SkeletonProps) {
  return (
    <div
      className={cn("skeleton-shimmer", className)}
      style={{ width, height, borderRadius: radiusMap[rounded], ...style }}
      {...props}
    />
  );
}

/* ── Pre-composed variants ─────────────────────────────── */

export function SkeletonRow() {
  return (
    <div
      className="flex items-center gap-4 px-4"
      style={{
        height: 52,
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      {/* Avatar */}
      <Skeleton width={32} height={32} rounded="full" style={{ flexShrink: 0 }} />
      {/* Name + email */}
      <div className="flex flex-col gap-1.5 flex-1">
        <Skeleton height={11} width="32%" />
        <Skeleton height={10} width="20%" />
      </div>
      {/* Company */}
      <Skeleton height={10} width="16%" />
      {/* Status badge */}
      <Skeleton height={20} width={52} rounded="sm" />
      {/* Actions */}
      <Skeleton width={24} height={24} rounded="sm" style={{ flexShrink: 0 }} />
    </div>
  );
}

export function SkeletonTable({ rows = 6 }: { rows?: number }) {
  return (
    <div>
      {/* Header */}
      <div
        className="flex items-center gap-4 px-4"
        style={{
          height: 40,
          borderBottom: "1px solid var(--border-default)",
          background: "var(--bg-base)",
        }}
      >
        <Skeleton height={9} width="14%" />
        <Skeleton height={9} width="18%" />
        <Skeleton height={9} width="12%" />
        <Skeleton height={9} width="10%" />
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonRow key={i} />
      ))}
    </div>
  );
}

export function SkeletonCard() {
  return (
    <div
      style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-lg)",
        padding: 20,
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <div className="flex items-center gap-3">
        <Skeleton width={36} height={36} rounded="full" />
        <div className="flex flex-col gap-2 flex-1">
          <Skeleton height={12} width="50%" />
          <Skeleton height={10} width="30%" />
        </div>
      </div>
      <Skeleton height={10} width="90%" />
      <Skeleton height={10} width="70%" />
    </div>
  );
}
