import { SectionCard } from '@/components/common/SectionCard';
import { useDashboardStore } from '@/store/useDashboardStore';

export function CustomersPage() {
  const leads = useDashboardStore((s) => s.leads);

  return (
    <SectionCard title="Customer Intelligence" subtitle="Intent, model interest, objections and loss reasons per lead">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {leads.slice(0, 24).map((lead) => (
          <article key={lead.id} className="rounded-2xl border border-slate-100 bg-slate-50 p-4 text-sm">
            <h3 className="font-semibold">{lead.name ?? lead.mobile}</h3>
            <p className="text-slate-500">Intent: {lead.intent ?? 'Inquiry'}</p>
            <p>Interested Model: {lead.interested_model ?? 'N/A'}</p>
            <p>Objections: {lead.objections?.join(', ') || 'None captured'}</p>
            <p>Lost Reason: {lead.lost_reason ?? '—'}</p>
          </article>
        ))}
      </div>
    </SectionCard>
  );
}
