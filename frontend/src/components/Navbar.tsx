import React from 'react';
import {
  Activity,
  Calendar,
  Users,
  ShieldCheck,
  AlertTriangle,
  Cpu,
  RotateCcw,
  Play,
  Radio,
  Clock,
  Layers,
  Plane,
  Sun,
  Moon,
} from 'lucide-react';
import { NavTab } from '../types';
import { ConnectionStatus } from '../hooks/useWebSocket';

interface NavbarProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  wsStatus: ConnectionStatus;
  lastUpdateUtc: number;
  onGenerateRoster: () => void;
  onResetDemo: (profile: 'demo' | 'test') => void;
  isGenerating: boolean;
  isResetting: boolean;
  eventCount: number;
  onToggleEventsDrawer: () => void;
  isEventsDrawerOpen: boolean;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  currentTab,
  onSelectTab,
  wsStatus,
  lastUpdateUtc,
  onGenerateRoster,
  onResetDemo,
  isGenerating,
  isResetting,
  eventCount,
  onToggleEventsDrawer,
  isEventsDrawerOpen,
  theme,
  onToggleTheme,
}) => {
  const tabs: { id: NavTab; label: string; icon: React.ReactNode }[] = [
    { id: 'overview', label: 'Operations Overview', icon: <Activity className="w-4 h-4" /> },
    { id: 'schedule', label: 'Flight Schedule', icon: <Plane className="w-4 h-4" /> },
    { id: 'roster', label: 'Roster Planner', icon: <Calendar className="w-4 h-4" /> },
    { id: 'crew', label: 'Crew Directory', icon: <Users className="w-4 h-4" /> },
    { id: 'fleet', label: 'Aircraft Fleet', icon: <Layers className="w-4 h-4" /> },
    { id: 'constraints', label: 'Constraint Inspector', icon: <ShieldCheck className="w-4 h-4" /> },
    { id: 'disruptions', label: 'Disruption Simulator', icon: <AlertTriangle className="w-4 h-4" /> },
    { id: 'laboratory', label: 'ADS Laboratory', icon: <Cpu className="w-4 h-4" /> },
  ];

  const formatUtcTime = (epochSeconds: number) => {
    if (!epochSeconds) return '--:--:-- UTC';
    const date = new Date(epochSeconds * 1000);
    return date.toISOString().substring(11, 19) + ' UTC';
  };

  return (
    <header className="sticky top-0 z-40 bg-white/95 dark:bg-slate-950/95 backdrop-blur-md border-b border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100 shadow-xs">
      {/* Top Bar: Brand, Rule Profile, Live Status, System Controls */}
      <div className="flex flex-wrap items-center justify-between px-4 py-2 border-b border-slate-200/80 dark:border-slate-800/80 gap-2">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-sky-500/15 border border-sky-500/30 dark:bg-cyan-600/30 dark:border-cyan-500/50 flex items-center justify-center text-sky-700 dark:text-cyan-400 font-bold text-xs tracking-wider">
              NV
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm tracking-tight text-slate-900 dark:text-white">AirCrewOps</span>
                <span className="text-slate-300 dark:text-slate-600 text-xs">|</span>
                <span className="text-sky-700 dark:text-cyan-400 font-semibold text-xs tracking-wide">Nova Air SOC</span>
              </div>
              <div className="text-[10px] text-slate-500 dark:text-slate-400 font-mono">System Operations Control</div>
            </div>
          </div>

          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-700/70 text-[11px] text-slate-700 dark:text-slate-300">
            <span className="w-1.5 h-1.5 rounded-full bg-sky-600 dark:bg-cyan-400"></span>
            <span className="font-mono text-sky-700 dark:text-cyan-300 font-medium">nova_air_demo_v1</span>
            <span className="text-slate-400 dark:text-slate-600">·</span>
            <span className="text-[10px] uppercase tracking-wider text-amber-700 dark:text-amber-400/90 font-semibold">Educational Simulator</span>
          </div>
        </div>

        {/* Live Telemetry & Actions */}
        <div className="flex items-center gap-3 text-xs">
          {/* WebSocket Status Pill */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
            <span
              className={`w-2 h-2 rounded-full ${
                wsStatus === 'connected'
                  ? 'bg-emerald-500 dark:bg-emerald-400 animate-pulse'
                  : wsStatus === 'connecting'
                  ? 'bg-amber-500 dark:bg-amber-400 animate-ping'
                  : 'bg-rose-500'
              }`}
            />
            <span className="capitalize font-mono text-[11px] font-medium text-slate-700 dark:text-slate-300">
              {wsStatus === 'connected' ? 'LIVE' : wsStatus}
            </span>
          </div>

          {/* Clock UTC */}
          <div className="hidden md:flex items-center gap-1.5 text-slate-600 dark:text-slate-400 font-mono text-[11px]">
            <Clock className="w-3.5 h-3.5 text-slate-400 dark:text-slate-500" />
            <span>{formatUtcTime(lastUpdateUtc)}</span>
          </div>

          {/* Action: Generate Roster */}
          <button
            onClick={onGenerateRoster}
            disabled={isGenerating}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 active:bg-sky-700 disabled:opacity-50 text-white font-semibold text-xs shadow-sm transition active:scale-95"
            title="Run priority queue heuristic roster optimization"
          >
            <Play className={`w-3.5 h-3.5 ${isGenerating ? 'animate-spin' : ''}`} />
            <span>{isGenerating ? 'Generating...' : 'Generate Roster'}</span>
          </button>

          {/* Action: Reset Demo Dropdown */}
          <div className="flex items-center rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-sm overflow-hidden text-xs">
            <button
              onClick={() => onResetDemo('demo')}
              disabled={isResetting}
              className="px-2.5 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 flex items-center gap-1.5 transition font-medium"
              title="Reset state and reload Demo dataset (36 flights, 8 aircraft, 42 crew)"
            >
              <RotateCcw className={`w-3 h-3 text-amber-500 dark:text-amber-400 ${isResetting ? 'animate-spin' : ''}`} />
              <span>Reset Demo</span>
            </button>
            <button
              onClick={() => onResetDemo('test')}
              disabled={isResetting}
              className="px-2 py-1.5 border-l border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-[11px] text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition font-mono"
              title="Reset to Test dataset profile (14 flights)"
            >
              Test
            </button>
          </div>

          {/* Action: Toggle Events Drawer */}
          <button
            onClick={onToggleEventsDrawer}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition shadow-sm ${
              isEventsDrawerOpen
                ? 'bg-sky-50 border-sky-300 text-sky-700 dark:bg-slate-800 dark:border-cyan-500/50 dark:text-cyan-300'
                : 'bg-white border-slate-300 text-slate-700 hover:bg-slate-50 dark:bg-slate-900 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-800'
            }`}
          >
            <Radio className="w-3.5 h-3.5 text-sky-600 dark:text-cyan-400" />
            <span>Events</span>
            {eventCount > 0 && (
              <span className="ml-0.5 px-1.5 py-0.2 rounded-full bg-sky-100 text-sky-800 dark:bg-cyan-500/20 dark:text-cyan-300 text-[10px] font-mono font-semibold">
                {eventCount}
              </span>
            )}
          </button>

          {/* Action: Theme Switcher (White/Light vs Dark) */}
          <button
            onClick={onToggleTheme}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition active:scale-95 text-xs font-medium shadow-sm"
            title={theme === 'light' ? 'Switch to Dark Theme' : 'Switch to White/Light Theme'}
          >
            {theme === 'light' ? (
              <>
                <Sun className="w-3.5 h-3.5 text-amber-500" />
                <span>Light</span>
              </>
            ) : (
              <>
                <Moon className="w-3.5 h-3.5 text-cyan-400" />
                <span>Dark</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Navigation Tabs Bar */}
      <nav className="flex items-center overflow-x-auto scrollbar-none px-3 bg-white dark:bg-slate-950 border-t border-slate-200 dark:border-slate-800/80 gap-1">
        {tabs.map((tab) => {
          const isActive = currentTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onSelectTab(tab.id)}
              className={`flex items-center gap-2 px-3.5 py-2.5 text-xs font-medium whitespace-nowrap border-b-2 transition-all ${
                isActive
                  ? 'border-sky-600 text-sky-700 bg-sky-50 font-semibold dark:border-cyan-400 dark:text-cyan-300 dark:bg-slate-900/60'
                  : 'border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-100/70 dark:text-slate-400 dark:hover:text-slate-200 dark:hover:bg-slate-900/30'
              }`}
            >
              <span className={isActive ? 'text-sky-600 dark:text-cyan-400' : 'text-slate-400 dark:text-slate-500'}>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          );
        })}
      </nav>
    </header>
  );
};
