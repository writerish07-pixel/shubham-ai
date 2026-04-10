import { useMemo, useState } from 'react';
import { SectionCard } from '@/components/common/SectionCard';
import { SalesCharts } from '@/components/SalesCharts';
import { useDashboardStore } from '@/store/useDashboardStore';

export function SalesPage() {
  const [modelFilter, setModelFilter] = useState('all');
  const leads = useDashboardStore((s) => s.leads);

  const models = useMemo(() => ['all', ...new Set(leads.map((lead) => lead.interested_model).filter(Boolean) as string[])], [leads]);

  const filtered = leads.filter((lead) => modelFilter === 'all' || lead.interested_model === modelFilter);

  return (
    <SectionCard
      title="Sales Intelligence"
      subtitle="Performance, objections, and competitor pressure trends"
      action={
        <select value={modelFilter} onChange={(e) => setModelFilter(e.target.value)} className="rounded-lg border border-slate-200 px-3 py-2 text-sm">
          {models.map((model) => (
            <option key={model} value={model}>
              {model}
            </option>
          ))}
        </select>
      }
    >
      <SalesCharts />
      <div className="mt-4 overflow-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-slate-500">
            <tr>
              <th className="py-2">Customer</th>
              <th>Model</th>
              <th>Status</th>
              <th>Intent</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 20).map((lead) => (
              <tr key={lead.id} className="border-t border-slate-100">
                <td className="py-2">{lead.name ?? 'Unknown'}</td>
                <td>{lead.interested_model ?? '—'}</td>
                <td className="capitalize">{lead.status ?? 'new'}</td>
                <td>{lead.intent ?? 'inquiry'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}
