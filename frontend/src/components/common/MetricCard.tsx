interface MetricCardProps {
  label: string;
  value: string | number;
  tone?: 'default' | 'good' | 'warn' | 'bad';
}

export function MetricCard({ label, value, tone = 'default' }: MetricCardProps) {
  const tones = {
    default: 'from-brand-50 to-white text-brand-600',
    good: 'from-emerald-50 to-white text-emerald-700',
    warn: 'from-amber-50 to-white text-amber-700',
    bad: 'from-rose-50 to-white text-rose-700'
  };

  return (
    <article className={`rounded-2xl bg-gradient-to-br p-4 ${tones[tone]}`}>
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </article>
  );
}
