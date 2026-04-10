import { PropsWithChildren } from 'react';
import { NavLink } from 'react-router-dom';
import { ChartBarIcon, CpuChipIcon, DocumentArrowUpIcon, HomeIcon, PhoneIcon, UserGroupIcon } from '@heroicons/react/24/outline';
import classNames from 'classnames';

const navItems = [
  { to: '/', label: 'Overview', icon: HomeIcon },
  { to: '/calls', label: 'Live Calls', icon: PhoneIcon },
  { to: '/sales', label: 'Sales Analytics', icon: ChartBarIcon },
  { to: '/learning', label: 'Learning', icon: CpuChipIcon },
  { to: '/uploads', label: 'Uploads', icon: DocumentArrowUpIcon },
  { to: '/customers', label: 'Customer Intel', icon: UserGroupIcon },
  { to: '/admin', label: 'Hybrid Rules', icon: CpuChipIcon }
];

export function AppShell({ children }: PropsWithChildren) {
  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="mx-auto grid max-w-[1600px] grid-cols-1 gap-5 p-4 md:grid-cols-[260px_1fr]">
        <aside className="glass rounded-3xl p-4 shadow-card">
          <h1 className="mb-6 text-lg font-semibold">Hero Voice AI</h1>
          <nav className="space-y-2">
            {navItems.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  classNames('flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition', {
                    'bg-brand-500 text-white': isActive,
                    'text-slate-700 hover:bg-slate-100': !isActive
                  })
                }
              >
                <Icon className="h-5 w-5" />
                {label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <main className="space-y-4">{children}</main>
      </div>
    </div>
  );
}
