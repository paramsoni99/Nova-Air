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
    <header className="sticky top-0 z-40 bg-slate-950/95 backdrop-blur border-b border-slate-800 text-slate-100 shadow-md">
      {/* Top Bar: Brand, Rule Profile, Live Status, System Controls */}
      <div className="flex flex-wrap items-center justify-between px-4 py-2 border-b border-slate-800/80 gap-2">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-cyan-600/30 border border-cyan-500/50 flex items-center justify-center text-cyan-400 font-bold text-xs tracking-wider">
              NV
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-sm tracking-wide text-white">AirCrewOps</span>
                <span className="text-slate-400 text-xs">|</span>
                <span className="text-cyan-400 font-semibold text-xs tracking-wide">Nova Air SOC</span>
              </div>
              <div className="text-[10px] text-slate-500 font-mono">System Operations Control</div>
            </div>
          </div>

          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-slate-900 border border-slate-700/70 text-[11px] text-slate-300">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
            <span className="font-mono text-cyan-300 font-medium">nova_air_demo_v1</span>
            <span className="text-slate-500">·</span>
            <span className="text-[10px] uppercase tracking-wider text-amber-400/90 font-semibold">Educational Simulator</span>
          </div>
        </div>

        {/* Live Telemetry & Actions */}
        <div className="flex items-center gap-3 text-xs">
          {/* WebSocket Status Pill */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-900 border border-slate-800">
            <span
              className={`w-2 h-2 rounded-full ${
                wsStatus === 'connected'
                  ? 'bg-emerald-400 animate-pulse'
                  : wsStatus === 'connecting'
                  ? 'bg-amber-400 animate-ping'
                  : 'bg-rose-500'
              }`}
            />
            <span className="capitalize font-mono text-[11px] text-slate-300">
              {wsStatus === 'connected' ? 'LIVE' : wsStatus}
            </span>
          </div>

          {/* Clock UTC */}
          <div className="hidden md:flex items-center gap-1.5 text-slate-400 font-mono text-[11px]">
            <Clock className="w-3.5 h-3.5 text-slate-500" />
            <span>{formatUtcTime(lastUpdateUtc)}</span>
          </div>

          {/* Action: Generate Roster */}
          <button
            onClick={onGenerateRoster}
            disabled={isGenerating}
            className="flex items-center gap-1.5 px-3 py-1 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-medium shadow-sm transition active:scale-95"
            title="Run priority queue heuristic roster optimization"
          >
            <Play className={`w-3.5 h-3.5 ${isGenerating ? 'animate-spin' : ''}`} />
            <span>{isGenerating ? 'Generating...' : 'Generate Roster'}</span>
          </button>

          {/* Action: Reset Demo Dropdown */}
          <div className="flex items-center rounded border border-slate-700 bg-slate-900 overflow-hidden">
            <button
              onClick={() => onResetDemo('demo')}
              disabled={isResetting}
              className="px-2.5 py-1 hover:bg-slate-800 text-slate-300 hover:text-white flex items-center gap-1 transition"
              title="Reset state and reload Demo dataset (36 flights, 8 aircraft, 42 crew)"
            >
              <RotateCcw className={`w-3 h-3 text-amber-400 ${isResetting ? 'animate-spin' : ''}`} />
              <span>Reset Demo</span>
            </button>
            <button
              onClick={() => onResetDemo('test')}
              disabled={isResetting}
              className="px-2 py-1 border-l border-slate-800 hover:bg-slate-800 text-[11px] text-slate-400 hover:text-white transition"
              title="Reset to Test dataset profile (14 flights)"
            >
              Test
            </button>
          </div>

          {/* Action: Toggle Events Drawer */}
          <button
            onClick={onToggleEventsDrawer}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded border transition ${
              isEventsDrawerOpen
                ? 'bg-slate-800 border-cyan-500/50 text-cyan-300'
                : 'bg-slate-900 border-slate-800 text-slate-300 hover:bg-slate-800'
            }`}
          >
            <Radio className="w-3.5 h-3.5 text-cyan-400" />
            <span>Events</span>
            {eventCount > 0 && (
              <span className="ml-0.5 px-1.5 py-0.2 rounded-full bg-cyan-500/20 text-cyan-300 text-[10px] font-mono font-semibold">
                {eventCount}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Navigation Tabs Bar */}
      <nav className="flex items-center overflow-x-auto scrollbar-none px-2 bg-slate-950">
        {tabs.map((tab) => {
          const isActive = currentTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onSelectTab(tab.id)}
              className={`flex items-center gap-2 px-3.5 py-2.5 text-xs font-medium whitespace-nowrap border-b-2 transition-all ${
                isActive
                  ? 'border-cyan-400 text-cyan-300 bg-slate-900/60'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/30'
              }`}
            >
              <span className={isActive ? 'text-cyan-400' : 'text-slate-500'}>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          );
        })}
      </nav>
    </header>
  );
};
