"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

interface MarkdownContentProps {
  content: string;
}

const components: Components = {
  p({ children }) {
    return (
      <p
        style={{
          margin: "0 0 0.6em 0",
          color: "var(--text-primary)",
          lineHeight: "1.7",
        }}
      >
        {children}
      </p>
    );
  },
  strong({ children }) {
    return (
      <strong
        style={{
          color: "var(--white-spectral)",
          fontWeight: 600,
        }}
      >
        {children}
      </strong>
    );
  },
  em({ children }) {
    return (
      <em style={{ color: "var(--gray-silver)", fontStyle: "italic" }}>{children}</em>
    );
  },
  h1({ children }) {
    return (
      <h1
        style={{
          fontSize: "1.1em",
          fontWeight: 700,
          color: "var(--white-spectral)",
          borderBottom: "1px solid var(--chat-tool-border)",
          paddingBottom: "0.3em",
          marginBottom: "0.6em",
          letterSpacing: "0.02em",
          fontFamily: "var(--font-title)",
        }}
      >
        {children}
      </h1>
    );
  },
  h2({ children }) {
    return (
      <h2
        style={{
          fontSize: "1em",
          fontWeight: 600,
          color: "var(--white-spectral)",
          borderBottom: "1px solid var(--chat-tool-border)",
          paddingBottom: "0.25em",
          marginBottom: "0.5em",
          letterSpacing: "0.02em",
        }}
      >
        {children}
      </h2>
    );
  },
  h3({ children }) {
    return (
      <h3
        style={{
          fontSize: "0.9em",
          fontWeight: 600,
          color: "var(--gray-silver)",
          marginBottom: "0.4em",
          textTransform: "uppercase",
          letterSpacing: "0.07em",
        }}
      >
        {children}
      </h3>
    );
  },
  ul({ children }) {
    return (
      <ul
        style={{
          margin: "0 0 0.6em 0",
          paddingLeft: "1.2em",
          listStyleType: "none",
        }}
      >
        {children}
      </ul>
    );
  },
  ol({ children }) {
    return (
      <ol
        style={{
          margin: "0 0 0.6em 0",
          paddingLeft: "1.4em",
          listStyleType: "decimal",
          color: "var(--text-primary)",
        }}
      >
        {children}
      </ol>
    );
  },
  li({ children }) {
    return (
      <li
        style={{
          position: "relative",
          paddingLeft: "0.8em",
          marginBottom: "0.25em",
          color: "var(--text-primary)",
        }}
      >
        <span
          style={{
            position: "absolute",
            left: 0,
            top: "0.55em",
            width: "4px",
            height: "4px",
            borderRadius: "50%",
            background: "var(--accent-red)",
            display: "inline-block",
          }}
        />
        {children}
      </li>
    );
  },
  table({ children }) {
    return (
      <div style={{ overflowX: "auto", marginBottom: "0.6em" }}>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "0.82em",
            fontFamily: "var(--font-body)",
          }}
        >
          {children}
        </table>
      </div>
    );
  },
  thead({ children }) {
    return (
      <thead
        style={{
          background: "rgba(192, 0, 0, 0.08)",
          borderBottom: "1px solid var(--chat-tool-border)",
        }}
      >
        {children}
      </thead>
    );
  },
  th({ children }) {
    return (
      <th
        style={{
          padding: "0.45em 0.75em",
          textAlign: "left",
          fontWeight: 600,
          color: "var(--gray-silver)",
          letterSpacing: "0.06em",
          fontSize: "0.78em",
          textTransform: "uppercase",
          whiteSpace: "nowrap",
          borderRight: "1px solid rgba(255,255,255,0.04)",
        }}
      >
        {children}
      </th>
    );
  },
  td({ children }) {
    return (
      <td
        style={{
          padding: "0.4em 0.75em",
          color: "var(--text-primary)",
          borderBottom: "1px solid rgba(255,255,255,0.04)",
          borderRight: "1px solid rgba(255,255,255,0.03)",
          verticalAlign: "top",
        }}
      >
        {children}
      </td>
    );
  },
  code({ children, className }) {
    const isBlock = Boolean(className);
    if (isBlock) {
      return (
        <code
          className="font-mono-geist"
          style={{
            display: "block",
            background: "rgba(0,0,0,0.35)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "6px",
            padding: "0.6em 0.85em",
            fontSize: "0.78em",
            color: "var(--white-spectral)",
            overflowX: "auto",
            lineHeight: "1.6",
          }}
        >
          {children}
        </code>
      );
    }
    return (
      <code
        className="font-mono-geist"
        style={{
          background: "rgba(192, 0, 0, 0.1)",
          border: "1px solid rgba(192, 0, 0, 0.2)",
          borderRadius: "4px",
          padding: "0.1em 0.4em",
          fontSize: "0.82em",
          color: "var(--mcp-crm)",
        }}
      >
        {children}
      </code>
    );
  },
  pre({ children }) {
    return (
      <pre
        style={{
          margin: "0 0 0.6em 0",
          background: "rgba(0,0,0,0.35)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "6px",
          padding: "0.6em 0.85em",
          overflowX: "auto",
        }}
      >
        {children}
      </pre>
    );
  },
  blockquote({ children }) {
    return (
      <blockquote
        style={{
          borderLeft: "3px solid var(--accent-red)",
          paddingLeft: "0.85em",
          margin: "0 0 0.6em 0",
          color: "var(--text-secondary)",
          fontStyle: "italic",
        }}
      >
        {children}
      </blockquote>
    );
  },
  hr() {
    return (
      <hr
        style={{
          border: "none",
          borderTop: "1px solid var(--chat-tool-border)",
          margin: "0.7em 0",
        }}
      />
    );
  },
  a({ children, href }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        style={{
          color: "var(--mcp-crm)",
          textDecoration: "underline",
          textDecorationColor: "rgba(255,80,80,0.4)",
        }}
      >
        {children}
      </a>
    );
  },
};

export function MarkdownContent({ content }: MarkdownContentProps) {
  return (
    <div style={{ lineHeight: "1.7" }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
