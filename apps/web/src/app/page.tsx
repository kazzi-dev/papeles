import { AskBox } from "@/components/ask-box";

const AGENCIES = ["SSS", "PhilHealth", "Pag-IBIG", "PSA", "NBI", "PhilSys", "LTO"];

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-8 px-4 py-12 sm:py-20">
      <header className="space-y-3">
        <h1 className="text-4xl font-bold tracking-tight">Papeles</h1>
        <p className="text-lg text-zinc-600 dark:text-zinc-400">
          Know exactly what to bring before you line up. Ask about any government document in
          English, Tagalog, or Bisaya. Answers come from official agency pages, with links.
        </p>
        <ul className="flex flex-wrap gap-2 pt-1" aria-label="Covered agencies">
          {AGENCIES.map((a) => (
            <li
              key={a}
              className="rounded-md bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-950 dark:text-blue-200"
            >
              {a}
            </li>
          ))}
        </ul>
      </header>

      <AskBox />

      <footer className="mt-auto pt-8 text-xs text-zinc-500">
        Papeles is a community project and is not affiliated with any government agency.
      </footer>
    </main>
  );
}
