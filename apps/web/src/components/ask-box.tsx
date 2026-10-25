"use client";

import { useState, type FormEvent } from "react";

import { Answer } from "@/components/answer";
import { ask, LANGS, type AskResponse, type Lang } from "@/lib/api";

const EXAMPLES = [
  "Nakalimutan ko ang Pag-IBIG MID number ko, paano ko makukuha?",
  "How do I order a PSA birth certificate online?",
  "Unsaon pag-register sa My.SSS?",
];

export function AskBox() {
  const [question, setQuestion] = useState("");
  const [lang, setLang] = useState<Lang>("en");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (question.trim().length < 3) return;
    setLoading(true);
    setError(null);
    try {
      setResult(await ask(question.trim(), lang));
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="w-full space-y-6">
      <form onSubmit={onSubmit} className="space-y-3">
        <label htmlFor="question" className="sr-only">
          Your question
        </label>
        <textarea
          id="question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about a passport, NBI clearance, SSS, PhilHealth..."
          rows={3}
          maxLength={1000}
          className="w-full rounded-xl border border-zinc-300 bg-white p-4 text-base shadow-sm outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-600/20 dark:border-zinc-700 dark:bg-zinc-900"
        />
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value as Lang)}
            aria-label="Answer language"
            className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          >
            {LANGS.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={loading || question.trim().length < 3}
            className="ml-auto rounded-lg bg-blue-700 px-5 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-50"
          >
            {loading ? "Hinahanap..." : "Ask"}
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => setQuestion(ex)}
              className="rounded-full border border-zinc-300 px-3 py-1 text-xs text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800"
            >
              {ex}
            </button>
          ))}
        </div>
      </form>

      {error && (
        <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
          {error}
        </p>
      )}

      {result && (
        <section aria-live="polite" className="space-y-4 rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <Answer text={result.answer} />
          {result.sources.length > 0 && (
            <div>
              <h2 className="mb-2 text-sm font-semibold text-zinc-500">Sources</h2>
              {/* Only cited sources are listed, so numbers can skip; show them explicitly. */}
              <ul className="space-y-1 text-sm">
                {result.sources.map((s) => (
                  <li key={s.url} id={`source-${s.n}`} className="flex gap-2 scroll-mt-4">
                    <span className="text-zinc-500">[{s.n}]</span>
                    <a href={s.url} target="_blank" rel="noreferrer" className="text-blue-700 underline dark:text-blue-400">
                      {s.agency}: {s.title}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-xs text-zinc-500">
            Requirements and fees change. Always confirm with the agency before you go.
          </p>
        </section>
      )}
    </div>
  );
}
