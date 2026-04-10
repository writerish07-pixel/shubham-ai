import { useDashboardStore } from '@/store/useDashboardStore';

const toneMap = {
  listening: 'bg-slate-100 text-slate-600',
  'user-speaking': 'bg-amber-100 text-amber-700',
  'ai-speaking': 'bg-emerald-100 text-emerald-700'
};

export function AgentStatePill() {
  const state = useDashboardStore((s) => s.agentState);
  return <span className={`rounded-full px-3 py-1 text-xs font-medium ${toneMap[state]}`}>{state.replace('-', ' ')}</span>;
}
