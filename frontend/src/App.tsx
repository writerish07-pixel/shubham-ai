import { Route, Routes } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import { useAutoRefresh } from '@/hooks/useAutoRefresh';
import { useRealtimeCallStream } from '@/hooks/useRealtimeCallStream';
import { AdminRulesPage } from '@/pages/AdminRulesPage';
import { CustomersPage } from '@/pages/CustomersPage';
import { LearningPage } from '@/pages/LearningPage';
import { LiveCallsPage } from '@/pages/LiveCallsPage';
import { OverviewPage } from '@/pages/OverviewPage';
import { SalesPage } from '@/pages/SalesPage';
import { UploadsPage } from '@/pages/UploadsPage';
import { useDashboardStore } from '@/store/useDashboardStore';

function App() {
  const refresh = useDashboardStore((s) => s.refresh);
  const error = useDashboardStore((s) => s.error);
  const loading = useDashboardStore((s) => s.loading);

  useAutoRefresh(refresh, 8000);
  useRealtimeCallStream();

  return (
    <AppShell>
      <header className="glass flex items-center justify-between rounded-3xl p-4 shadow-card">
        <div>
          <h1 className="text-xl font-semibold">AI Voice Agent Dashboard</h1>
          <p className="text-sm text-slate-500">Production control panel for real-time sales and learning operations</p>
        </div>
        <button onClick={refresh} className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white">
          {loading ? 'Refreshing...' : 'Refresh Now'}
        </button>
      </header>
      {error ? <p className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p> : null}
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/calls" element={<LiveCallsPage />} />
        <Route path="/sales" element={<SalesPage />} />
        <Route path="/learning" element={<LearningPage />} />
        <Route path="/uploads" element={<UploadsPage />} />
        <Route path="/customers" element={<CustomersPage />} />
        <Route path="/admin" element={<AdminRulesPage />} />
      </Routes>
    </AppShell>
  );
}

export default App;
