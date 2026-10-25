import React from 'react';
import { X, Trash2, Radio, Clock } from 'lucide-react';
import { WebSocketEvent } from '../types';

interface EventDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  events: WebSocketEvent[];
  onClear: () => void;
}

export const EventDrawer: React.FC<EventDrawerProps> = ({
  isOpen,
  onClose,
  events,
  onClear,
}) => {
  if (!isOpen) return null;

  const formatTime = (epoch: number) => {
    if (!epoch) return '';
    const d = new Date(epoch * 1000);
    return d.toISOString().substring(11, 19);
  };

  const getEventBadge = (type: string) => {
    switch (type) {
      case 'ROSTER_GENERATED':
      case 'FLIGHT_ASSIGNED':
        return 'bg-emerald-900/40 text-emerald-300 border-emerald-700/50';
      case 'DISRUPTION_INJECTED':
      case 'FLIGHT_DELAYED':
      case 'AIRCRAFT_AOG':
      case 'PILOT_SICK':
        return 'bg-amber-900/40 text-amber-300 border-amber-700/50';
      case 'RULE_VIOLATION':
      case 'DISRUPTION_RECOVERY_FAILED':
        return 'bg-rose-900/40 text-rose-300 border-rose-700/50';
      case 'SYSTEM_RESET':
        return 'bg-cyan-900/40 text-cyan-300 border-cyan-700/50';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-md bg-slate-950 border-l border-slate-800 shadow-2xl flex flex-col transition-transform animate-in slide-in-from-right duration-200">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 bg-slate-900/80">
        <div className="flex items-center gap-2">
          <Radio className="w-4 h-4 text-cyan-400 animate-pulse" />
          <h2 className="text-sm font-semibold text-slate-100">Live Operations Event Stream</h2>
          <span className="px-2 py-0.5 rounded-full bg-slate-800 text-[10px] text-slate-400 font-mono">
            {events.length}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {events.length > 0 && (
            <button
              onClick={onClear}
              className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-slate-200"
              title="Clear events"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            onClick={onClose}
            className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-slate-200"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Events List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {events.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-center text-slate-500 text-xs">
            <Radio className="w-8 h-8 mb-2 stroke-1 text-slate-600" />
            <p>No real-time events recorded yet.</p>
            <p className="text-[11px] text-slate-600 mt-1">
              Events broadcast on schedule optimization, disruptions, or manual updates will appear here.
            </p>
          </div>
        ) : (
          events.map((ev, idx) => (
            <div
              key={idx}
              className="p-2.5 rounded-lg bg-slate-900/90 border border-slate-800/80 text-xs hover:border-slate-700 transition"
            >
              <div className="flex items-center justify-between mb-1.5">
                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold border ${getEventBadge(
                    ev.event_type
                  )}`}
                >
                  {ev.event_type}
                </span>
                <span className="flex items-center gap-1 text-[10px] font-mono text-slate-500">
                  <Clock className="w-3 h-3" />
                  {formatTime(ev.timestamp_utc)}
                </span>
              </div>
              <pre className="text-[11px] font-mono bg-slate-950 p-2 rounded text-slate-300 overflow-x-auto max-h-36 scrollbar-none">
                {JSON.stringify(ev.payload || {}, null, 2)}
              </pre>
            </div>
          ))
        )}
      </div>

      {/* Footer Invariant Note */}
      <div className="px-4 py-2 border-t border-slate-800/80 bg-slate-900/50 text-[10px] text-slate-500 font-mono">
        Strict Law: Events are broadcast strictly after transactional SQLite commit and ADS invariant synchronization.
      </div>
    </div>
  );
};
