import Markdown, { type Components } from "react-markdown";

// Turn bare citations like [2] into links to the matching entry in the sources list.
function linkCitations(text: string): string {
  return text.replace(/\[(\d+)\](?!\()/g, "[[$1]](#source-$1)");
}

const components: Components = {
  p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
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
