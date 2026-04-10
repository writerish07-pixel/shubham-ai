import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useDashboardStore } from '@/store/useDashboardStore';

const palette = ['#4f6ef7', '#34d399', '#fbbf24', '#f87171', '#a78bfa'];

export function SalesCharts() {
  const stats = useDashboardStore((s) => s.stats);
  const intelligence = useDashboardStore((s) => s.intelligence);

  const conversionData = [
    { name: 'Converted', value: stats?.converted ?? 0 },
    { name: 'Lost', value: stats?.dead ?? 0 },
    { name: 'In Funnel', value: (stats?.total ?? 0) - ((stats?.converted ?? 0) + (stats?.dead ?? 0)) }
  ];

  const objections = intelligence?.top_reasons?.map((item) => ({ name: item.reason, value: item.count })) ?? [];

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="h-72 rounded-2xl bg-slate-50 p-3">
        <ResponsiveContainer>
          <PieChart>
            <Pie data={conversionData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90}>
              {conversionData.map((_, index) => (
                <Cell key={index} fill={palette[index % palette.length]} />
              ))}
            </Pie>
            <Tooltip />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="h-72 rounded-2xl bg-slate-50 p-3">
        <ResponsiveContainer>
          <BarChart data={objections}>
            <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
            <XAxis dataKey="name" hide />
            <YAxis />
            <Tooltip />
            <Bar dataKey="value" fill="#4f6ef7" radius={[8, 8, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
