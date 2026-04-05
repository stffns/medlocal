import { useState } from 'react';
import { Stethoscope, Search, GraduationCap } from 'lucide-react';
import ConsultView from './components/ConsultView';
import SearchView from './components/SearchView';
import TrainView from './components/TrainView';

const TABS = [
  { id: 'consult', label: 'Consult', icon: Stethoscope },
  { id: 'search', label: 'Search', icon: Search },
  { id: 'train', label: 'Train', icon: GraduationCap },
];

export default function App() {
  const [tab, setTab] = useState('consult');

  return (
    <div className="h-screen flex flex-col max-w-2xl mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-accent/15 flex items-center justify-center">
            <Stethoscope size={18} className="text-accent" />
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight">MedLocal</h1>
            <p className="text-[10px] text-text-2 -mt-0.5">Clinical Decision Support</p>
          </div>
        </div>
        <span className="text-[10px] text-text-2 bg-surface-2 px-2 py-0.5 rounded-full">Offline</span>
      </header>

      {/* Content */}
      <main className="flex-1 min-h-0 overflow-hidden">
        {tab === 'consult' && <ConsultView />}
        {tab === 'search' && <SearchView />}
        {tab === 'train' && <TrainView />}
      </main>

      {/* Tab bar */}
      <nav className="flex border-t border-border shrink-0 bg-surface">
        {TABS.map(t => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex-1 flex flex-col items-center gap-0.5 py-2.5 transition text-xs
                ${active ? 'text-accent' : 'text-text-2 hover:text-text'}`}
            >
              <Icon size={20} strokeWidth={active ? 2.5 : 1.5} />
              <span className={`font-medium ${active ? 'font-semibold' : ''}`}>{t.label}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
