import { useEffect, useState } from 'react';

export default function App() {
  const [connection, setConnection] = useState('Проверяем подключение к API…');

  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    let active = true;
    fetch('/api/v1/info', { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error('API unavailable');
        const info = await response.json();
        if (info.status !== 'ready' || info.phase !== 3) throw new Error('Unexpected API');
        if (active) setConnection('API подключён · Phase 3');
      })
      .catch(() => {
        if (active) setConnection('API недоступен. Проверьте запуск backend и обновите страницу.');
      })
      .finally(() => clearTimeout(timeout));
    return () => { active = false; clearTimeout(timeout); controller.abort(); };
  }, []);

  return (
    <main className="mx-auto max-w-4xl px-6 py-20">
      <p className="text-sm font-semibold uppercase tracking-widest text-teal-400">Operations workspace</p>
      <h1 className="mt-4 text-4xl font-semibold tracking-tight">AI Operations Copilot</h1>
      <p className="mt-5 max-w-2xl text-lg text-slate-300">
        Рабочее пространство для анализа заказов, доставки и SLA с проверяемыми источниками.
      </p>
      <section className="mt-10 rounded-2xl border border-slate-700 bg-slate-900 p-6">
        <h2 className="text-xl font-medium">Каркас проекта готов</h2>
        <p role="status" className="mt-3 text-teal-300">{connection}</p>
        <p className="mt-4 text-slate-400">
          AI Chat, бизнес-данные и поиск по документам появятся в следующих фазах.
          Сейчас проверяем связку React → FastAPI.
        </p>
        <a className="mt-6 inline-block text-teal-300 underline underline-offset-4" href="http://localhost:8000/docs">
          Открыть API документацию
        </a>
      </section>
    </main>
  );
}
