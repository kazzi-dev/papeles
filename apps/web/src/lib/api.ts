export type Lang = "en" | "tl" | "ceb";

export const LANGS: { value: Lang; label: string }[] = [
  { value: "en", label: "English" },
  { value: "tl", label: "Tagalog" },
  { value: "ceb", label: "Bisaya" },
];

// `n` is the number the answer cites this source by, e.g. [2].
export type Source = { n: number; title: string; url: string; agency: string };

export type AskResponse = { answer: string; sources: Source[] };

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function ask(question: string, lang: Lang): Promise<AskResponse> {
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, lang }),
  });
  if (!res.ok) {
    throw new Error(`The server answered ${res.status}. Please try again.`);
  }
  return res.json();
}
