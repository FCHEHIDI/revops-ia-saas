import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, hint, className, id, style, ...props },
  ref
) {
  const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");

  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label
          htmlFor={inputId}
          className="text-xs font-medium tracking-widest uppercase"
          style={{ color: "var(--text-muted)" }}
        >
          {label}
        </label>
      )}
      <input
        ref={ref}
        id={inputId}
        className={cn(
          "w-full text-sm outline-none transition-all duration-200",
          "placeholder:opacity-40 disabled:opacity-50 disabled:cursor-not-allowed",
          className
        )}
        style={{
          background: "var(--bg-elevated)",
          border: error ? "1px solid rgba(255,0,0,0.5)" : "1px solid var(--border-default)",
          borderRadius: "var(--radius-input)",
          color: "var(--text-primary)",
          padding: "10px 14px",
          ...style,
        }}
        onFocus={(e) => {
          e.currentTarget.style.border = error
            ? "1px solid rgba(255,0,0,0.7)"
            : "1px solid rgba(63,79,255,0.5)";
          e.currentTarget.style.boxShadow = error ? "var(--shadow-glow)" : "var(--shadow-blue)";
          props.onFocus?.(e);
        }}
        onBlur={(e) => {
          e.currentTarget.style.border = error
            ? "1px solid rgba(255,0,0,0.5)"
            : "1px solid var(--border-default)";
          e.currentTarget.style.boxShadow = "none";
          props.onBlur?.(e);
        }}
        {...props}
      />
      {error && <p className="text-xs" style={{ color: "var(--accent-red)" }}>{error}</p>}
      {hint && !error && <p className="text-xs" style={{ color: "var(--text-muted)" }}>{hint}</p>}
    </div>
  );
});
