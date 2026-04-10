import { useEffect, useState } from 'react';
import { SectionCard } from '@/components/common/SectionCard';

interface HybridRule {
  id: string;
  trigger: string;
  response: string;
  enabled: boolean;
}

export function AdminRulesPage() {
  const [rules, setRules] = useState<HybridRule[]>([]);
  const [status, setStatus] = useState('');

  const load = async () => {
    try {
      const res = await fetch('/api/hybrid/rules');
      const data = await res.json();
      setRules(data.rules ?? []);
    } catch {
      setStatus('Failed to load hybrid rules.');
    }
  };

  useEffect(() => {
    load();
  }, []);

  const save = async (rule: HybridRule) => {
    setStatus('Saving...');
    try {
      await fetch(`/api/hybrid/rules/${rule.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(rule)
      });
      setStatus('Rule updated.');
      load();
    } catch {
      setStatus('Save failed.');
    }
  };

  return (
    <SectionCard title="Hybrid Model Control" subtitle="Edit script responses and toggle rules">
      <div className="space-y-3">
        {rules.map((rule) => (
          <div key={rule.id} className="rounded-xl bg-slate-50 p-3 text-sm">
            <input
              value={rule.trigger}
              onChange={(e) => setRules((prev) => prev.map((it) => (it.id === rule.id ? { ...it, trigger: e.target.value } : it)))}
              className="mb-2 w-full rounded border border-slate-200 px-2 py-1"
            />
            <textarea
              value={rule.response}
              onChange={(e) => setRules((prev) => prev.map((it) => (it.id === rule.id ? { ...it, response: e.target.value } : it)))}
              className="mb-2 h-20 w-full rounded border border-slate-200 px-2 py-1"
            />
            <label className="mr-2 inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={rule.enabled}
                onChange={(e) => setRules((prev) => prev.map((it) => (it.id === rule.id ? { ...it, enabled: e.target.checked } : it)))}
              />
              Enabled
            </label>
            <button onClick={() => save(rule)} className="rounded bg-brand-500 px-3 py-1 text-white">
              Save
            </button>
          </div>
        ))}
      </div>
      {status ? <p className="mt-3 text-sm text-slate-600">{status}</p> : null}
    </SectionCard>
  );
}
