import { Children, isValidElement, type ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";

// Must match GENERAL_HEADING in apps/api/app/rag.py. Everything under this heading comes from
// the model's general knowledge, not an official source, so it gets a warning style.
const GENERAL_PREFIXES = ["General guidance", "Pangkalahatang gabay", "Kinatibuk-ang giya"];

function textOf(node: ReactNode): string {
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children);
  return "";
}

function isGeneralHeading(children: ReactNode): boolean {
  const only = Children.toArray(children);
  if (only.length !== 1 || !isValidElement(only[0]) || only[0].type !== "strong") return false;
  const text = textOf(only[0]).trim();
  return GENERAL_PREFIXES.some((p) => text.startsWith(p));
}

// Turn bare citations like [2] into links to the matching entry in the sources list.
function linkCitations(text: string): string {
  return text.replace(/\[(\d+)\](?!\()/g, "[[$1]](#source-$1)");
}

const components: Components = {
  p: ({ children }) =>
    isGeneralHeading(children) ? (
      <p className="mt-5 mb-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-1.5 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
        ⚠ {children}
      </p>
    ) : (
      <p className="mb-3 last:mb-0">{children}</p>
    ),
  ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5">{children}</ol>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  // Answers are short; keep any heading the model writes at body size.
  h1: ({ children }) => <p className="mb-2 font-semibold">{children}</p>,
  h2: ({ children }) => <p className="mb-2 font-semibold">{children}</p>,
  h3: ({ children }) => <p className="mb-2 font-semibold">{children}</p>,
  blockquote: ({ children }) => (
    <blockquote className="mb-3 border-l-2 border-zinc-300 pl-3 text-zinc-600 dark:border-zinc-700 dark:text-zinc-400">
      {children}
    </blockquote>
  ),
  a: ({ href, children }) =>
    href?.startsWith("#source-") ? (
      <a href={href} className="text-xs font-medium text-blue-700 no-underline dark:text-blue-400">
        {children}
      </a>
    ) : (
      <a href={href} target="_blank" rel="noreferrer" className="text-blue-700 underline dark:text-blue-400">
        {children}
      </a>
    ),
};

export function Answer({ text }: { text: string }) {
  return (
    <div className="leading-7">
      <Markdown components={components}>{linkCitations(text)}</Markdown>
    </div>
  );
}
