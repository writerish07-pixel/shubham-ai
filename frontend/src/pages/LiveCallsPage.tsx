import { SectionCard } from '@/components/common/SectionCard';
import { useDashboardStore } from '@/store/useDashboardStore';

export function LiveCallsPage() {
  const activeCalls = useDashboardStore((s) => s.activeCalls);
  const transcript = useDashboardStore((s) => s.transcript);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <SectionCard title="Active Call Sessions" subtitle="Real-time call status and call IDs">
        <div className="space-y-2">
          <p className="text-sm text-slate-600">Active: {activeCalls.active_calls}</p>
          {activeCalls.call_sids.map((callSid) => (
            <div key={callSid} className="rounded-xl bg-slate-50 p-3 text-sm font-medium text-slate-700">
              {callSid}
            </div>
          ))}
        </div>
      </SectionCard>
      <SectionCard title="Live Conversation" subtitle="User and AI turns streaming in near real-time">
        <div className="max-h-[520px] space-y-2 overflow-auto pr-2">
          {transcript.length === 0 ? <p className="text-sm text-slate-500">Waiting for live transcript...</p> : null}
          {transcript.map((turn, index) => (
            <div
              key={`${turn.timestamp}-${index}`}
              className={`rounded-2xl p-3 text-sm ${turn.speaker === 'user' ? 'bg-amber-50 text-amber-900' : 'bg-emerald-50 text-emerald-900'}`}
            >
              <p className="mb-1 text-xs uppercase">{turn.speaker}</p>
              <p>{turn.text}</p>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
