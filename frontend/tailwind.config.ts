import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        /* Backgrounds */
        background: "#0a0a0a",
        surface:    "#111111",
        elevated:   "#1a1a1a",
        sidebar:    "#0d001a",
        /* Accents */
        red: {
          DEFAULT: "#ff0000",
          dim:     "#4a0000",
          glow:    "rgba(255,0,0,0.18)",
        },
        blue: {
          DEFAULT: "#2979ff",
          dim:     "rgba(41,121,255,0.12)",
        },
        success: "#00ff88",
        warning: "#ff0066",
        /* Text */
        "text-primary":   "#f5f5f5",
        "text-secondary": "#999999",
        "text-muted":     "#555555",
        /* Borders */
        "border-subtle":  "#1f1f1f",
        "border-default": "#2a2a2a",
        "border-strong":  "#3a3a3a",
        /* Chat tokens (CSS var references) */
        "chat-tool":       "var(--chat-tool-text)",
        "chat-dot":        "var(--chat-dot)",
        "chat-cursor":     "var(--chat-cursor)",
        /* MCP service tokens */
        "mcp-crm":        "var(--mcp-crm)",
        "mcp-analytics":  "var(--mcp-analytics)",
        "mcp-billing":    "var(--mcp-billing)",
        "mcp-sequences":  "var(--mcp-sequences)",
        "mcp-default":    "var(--mcp-default)",
      },
      fontFamily: {
        sans:     ["Space Grotesk", "system-ui", "sans-serif"],
        orbitron: ["Orbitron", "monospace"],
      },
      borderRadius: {
        btn:   "12px",
        input: "8px",
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,0,0,0.9), 0 4px 16px rgba(0,0,0,0.7), inset 0 1px 0 rgba(255,255,255,0.025)",
        glow: "0 0 0 1px rgba(255,0,0,0.35), 0 4px 28px rgba(255,0,0,0.2)",
        blue: "0 0 0 1px rgba(63,79,255,0.4), 0 4px 28px rgba(63,79,255,0.22)",
        deep: "0 8px 48px rgba(0,0,0,0.95)",
      },
      animation: {
        "fade-in":   "fadeIn 0.4s ease forwards",
        "slide-up":  "slideUp 0.4s cubic-bezier(0.34,1.56,0.64,1) forwards",
        "glow-pulse": "glowPulse 2s ease-in-out infinite",
      },
      keyframes: {
        fadeIn:    { from: { opacity: "0" }, to: { opacity: "1" } },
        slideUp:   { from: { opacity: "0", transform: "translateY(16px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        glowPulse: { "0%,100%": { opacity: "0.6" }, "50%": { opacity: "1" } },
      },
    },
  },
  plugins: [],
};

export default config;
