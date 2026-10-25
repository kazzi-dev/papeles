import { isValidElement, type ReactNode } from "react";
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

// Models write the heading as bold text, a Markdown heading, or bold with a trailing line
// break, so match on the text rather than the exact element structure.
function isGeneralHeading(children: ReactNode): boolean {
  const text = textOf(children).trim();
  return text.length < 120 && GENERAL_PREFIXES.some((p) => text.startsWith(p));
}

function Block({ children, className }: { children: ReactNode; className: string }) {
  return isGeneralHeading(children) ? (
    <p className="mt-5 mb-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-1.5 text-sm font-semibold text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
      ⚠ {children}
    </p>
  ) : (
    <p className={className}>{children}</p>
  );
}

// Turn bare citations like [2] into links to the matching entry in the sources list.
function linkCitations(text: string): string {
  return text.replace(/\[(\d+)\](?!\()/g, "[[$1]](#source-$1)");
}

const components: Components = {
  p: ({ children }) => <Block className="mb-3 last:mb-0">{children}</Block>,
  ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5">{children}</ol>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  // Answers are short; keep any heading the model writes at body size.
  h1: ({ children }) => <Block className="mb-2 font-semibold">{children}</Block>,
  h2: ({ children }) => <Block className="mb-2 font-semibold">{children}</Block>,
  h3: ({ children }) => <Block className="mb-2 font-semibold">{children}</Block>,
  h4: ({ children }) => <Block className="mb-2 font-semibold">{children}</Block>,
  hr: () => <hr className="my-4 border-zinc-200 dark:border-zinc-800" />,
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
