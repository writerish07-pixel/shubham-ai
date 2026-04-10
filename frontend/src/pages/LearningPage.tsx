import { SectionCard } from '@/components/common/SectionCard';
import { useDashboardStore } from '@/store/useDashboardStore';

export function LearningPage() {
  const learning = useDashboardStore((s) => s.learningStatus);
  const intelligence = useDashboardStore((s) => s.intelligence);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <SectionCard title="Learning System Status" subtitle="RAG memory and embeddings health">
        <dl className="space-y-3 text-sm">
          <div className="flex justify-between"><dt>Enabled</dt><dd>{learning?.learning_enabled ? 'Yes' : 'No'}</dd></div>
          <div className="flex justify-between"><dt>Vectors</dt><dd>{learning?.vector_db_entries ?? 0}</dd></div>
          <div className="flex justify-between"><dt>Total Learnings</dt><dd>{learning?.total_learnings ?? 0}</dd></div>
          <div className="flex justify-between"><dt>Vector DB Status</dt><dd>{learning?.vector_db_status ?? 'Unknown'}</dd></div>
        </dl>
      </SectionCard>
      <SectionCard title="Insights" subtitle="Common objections and loss reasons">
        <div className="space-y-2 text-sm">
          {(intelligence?.top_reasons ?? []).map((item) => (
            <div key={item.reason} className="flex justify-between rounded-lg bg-slate-50 px-3 py-2">
              <span>{item.reason}</span>
              <strong>{item.count}</strong>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
