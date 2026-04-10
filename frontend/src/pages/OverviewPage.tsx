import { AgentStatePill } from '@/components/common/AgentStatePill';
import { MetricCard } from '@/components/common/MetricCard';
import { SectionCard } from '@/components/common/SectionCard';
import { SalesCharts } from '@/components/SalesCharts';
import { useDashboardStore } from '@/store/useDashboardStore';

export function OverviewPage() {
  const stats = useDashboardStore((s) => s.stats);
  const activeCalls = useDashboardStore((s) => s.activeCalls);

  return (
    <>
      <SectionCard title="Command Center" subtitle="Live dealership AI operations" action={<AgentStatePill />}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <MetricCard label="Total Calls" value={stats?.total ?? 0} />
          <MetricCard label="Leads Generated" value={(stats?.hot ?? 0) + (stats?.warm ?? 0)} tone="good" />
          <MetricCard label="Conversion Rate" value={`${stats?.conversion_rate ?? 0}%`} tone="good" />
          <MetricCard label="Lost Customers" value={stats?.dead ?? 0} tone="bad" />
          <MetricCard label="Active Calls" value={activeCalls.active_calls} tone="warn" />
        </div>
      </SectionCard>
      <SectionCard title="Sales Analytics" subtitle="Daily/weekly conversion and objections trends">
        <SalesCharts />
      </SectionCard>
    </>
  );
}
