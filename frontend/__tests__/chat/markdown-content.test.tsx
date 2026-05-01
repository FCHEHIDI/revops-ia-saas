/**
 * Unit tests for MarkdownContent component.
 * react-markdown is mocked — we test our component wrapper, not the library.
 */
import { render, screen } from "@testing-library/react";
import { MarkdownContent } from "@/components/chat/markdown-content";

// Mock react-markdown to avoid ESM-only dependency issues in Jest/CommonJS.
// The library itself is tested upstream — here we test our component wrapper.
jest.mock("react-markdown", () => {
  return function MockReactMarkdown({
    children,
    components: _comps,
  }: {
    children: string;
    components?: Record<string, unknown>;
  }) {
    return <div data-testid="markdown-output">{children}</div>;
  };
});

jest.mock("remark-gfm", () => () => {});

describe("MarkdownContent", () => {
  it("renders without crashing", () => {
    const { container } = render(<MarkdownContent content="Hello world" />);
    expect(container).toBeInTheDocument();
  });

  it("passes content to ReactMarkdown", () => {
    render(<MarkdownContent content="**bold text**" />);
    expect(screen.getByTestId("markdown-output")).toBeInTheDocument();
    expect(screen.getByTestId("markdown-output").textContent).toBe("**bold text**");
  });

  it("renders with empty string without crashing", () => {
    const { container } = render(<MarkdownContent content="" />);
    expect(container).toBeInTheDocument();
  });

  it("renders with multiline content", () => {
    render(<MarkdownContent content={"line 1\nline 2\nline 3"} />);
    expect(screen.getByTestId("markdown-output")).toBeInTheDocument();
  });
});
