import { createFileRoute, Link } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Piano lesson calendar" },
      {
        name: "description",
        content:
          "A calendar for a piano studio: lesson times for students, availability and packages for the teacher.",
      },
      { property: "og:title", content: "Piano lesson calendar" },
      {
        property: "og:description",
        content: "Lesson times for students, availability and packages for the teacher.",
      },
    ],
  }),
  component: Index,
});

function Index() {
  return (
    <main className="mx-auto w-full max-w-[560px] px-6 pt-16 pb-20">
      <h1 className="font-display text-5xl leading-tight">Piano lesson calendar</h1>
      <p className="mt-4 text-slate">
        Two surfaces, one studio. Lessons and availability come from the booking server.
      </p>

      <section className="mt-10">
        <h2 className="text-sm font-bold uppercase tracking-wide text-slate">Teacher</h2>
        <Link to="/admin" className="mt-2 inline-block text-felt underline underline-offset-4">
          Open studio admin
        </Link>
        <p className="text-sm text-slate">Password: piano</p>
      </section>

      <section className="mt-10">
        <h2 className="text-sm font-bold uppercase tracking-wide text-slate">Student links</h2>
        <p className="mt-2 text-sm text-slate">
          Students open the personal link supplied by their teacher.
        </p>
        <Link
          to="/s/$token"
          params={{ token: "anna" }}
          className="mt-2 inline-block text-sm text-felt underline underline-offset-4"
        >
          Open a seeded student example
        </Link>
      </section>
    </main>
  );
}
