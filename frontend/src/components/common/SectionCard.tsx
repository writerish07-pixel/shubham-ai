import { PropsWithChildren } from 'react';

interface Props {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export function SectionCard({ title, subtitle, action, children }: PropsWithChildren<Props>) {
  return (
    <section className="glass rounded-3xl p-5 shadow-card">
      <header className="mb-4 flex items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
          {subtitle ? <p className="text-sm text-slate-500">{subtitle}</p> : null}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}
