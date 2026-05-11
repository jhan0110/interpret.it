import { CreateSessionForm } from "./CreateSessionForm";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Interpretit</h1>
        <p className="mt-1 text-sm text-zinc-500">Operator dashboard</p>
      </div>
      <CreateSessionForm />
    </main>
  );
}
