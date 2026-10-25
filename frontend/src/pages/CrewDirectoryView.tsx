import React, { useState } from 'react';
import {
  Users,
  Search,
  Award,
  Calendar,
  X,
} from 'lucide-react';
import { CrewMember, DutyPeriod } from '../types';
import { api } from '../services/api';

interface CrewDirectoryViewProps {
  crewList: CrewMember[];
}

export const CrewDirectoryView: React.FC<CrewDirectoryViewProps> = ({
  crewList,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [baseFilter, setBaseFilter] = useState('');

  // Duty Timeline Modal State
  const [selectedCrew, setSelectedCrew] = useState<CrewMember | null>(null);
  const [dutySchedule, setDutySchedule] = useState<DutyPeriod[]>([]);
  const [isLoadingSchedule, setIsLoadingSchedule] = useState(false);

  const roles = ['CAPTAIN', 'FIRST_OFFICER', 'CABIN_CREW'];
  const bases = ['BOM', 'DEL', 'BLR', 'HYD', 'MAA', 'CCU', 'GOI'];

  const safeCrewList = Array.isArray(crewList) ? crewList : (crewList as any)?.crew || [];

  const filteredCrew = safeCrewList.filter((c: CrewMember) => {
    const matchesSearch =
      !searchQuery ||
      c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.id.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesRole = !roleFilter || c.role === roleFilter;
    const matchesBase = !baseFilter || c.home_base === baseFilter;
    return matchesSearch && matchesRole && matchesBase;
  });

  const handleOpenSchedule = async (crew: CrewMember) => {
    setSelectedCrew(crew);
    setIsLoadingSchedule(true);
    try {
      const schedule = await api.getCrewSchedule(crew.id);
      setDutySchedule(schedule);
    } catch {
      setDutySchedule([]);
    } finally {
      setIsLoadingSchedule(false);
    }
  };

  const formatUtcTime = (epochSeconds: number) => {
    if (!epochSeconds) return '--:--';
    const d = new Date(epochSeconds * 1000);
    return d.toISOString().replace('T', ' ').substring(5, 16) + 'Z';
  };

  const isExpired = (validUntilUtc: number) => {
    const now = Math.floor(Date.now() / 1000);
    return validUntilUtc < now;
  };

  return (
    <div className="space-y-5">
      {/* Top Bar: Search & Filters */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Users className="w-5 h-5 text-cyan-400" />
            <span>Crew Directory & Duty Index</span>
          </h2>
          <p className="text-xs text-slate-400">
            FDTL limits, type ratings, and RBIntervalTree duty interval tracking
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Search */}
          <div className="relative min-w-[180px]">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search crew by name or ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Role Filter */}
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="py-1.5 px-2.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-cyan-500"
          >
            <option value="">Role: All</option>
            {roles.map((r) => (
              <option key={r} value={r}>
                {r.replace('_', ' ')}
              </option>
            ))}
          </select>

          {/* Base Filter */}
          <select
            value={baseFilter}
            onChange={(e) => setBaseFilter(e.target.value)}
            className="py-1.5 px-2.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-cyan-500"
          >
            <option value="">Base: All</option>
            {bases.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Crew Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
        {filteredCrew.map((crew: CrewMember) => {
          const flightHours = crew.cumulative_flight_hours_7d || 0;
          const dutyHours = crew.cumulative_duty_hours_7d || 0;
          const maxFlight = 35; // 7-day DGCA limit
          const maxDuty = 60; // 7-day DGCA limit
          const flightPct = Math.min(100, Math.round((flightHours / maxFlight) * 100));
          const dutyPct = Math.min(100, Math.round((dutyHours / maxDuty) * 100));

          return (
            <div
              key={crew.id}
              className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition shadow-sm space-y-3"
            >
              {/* Header */}
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-bold text-white flex items-center gap-2">
                    <span>{crew.name}</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-cyan-300">
                      {crew.id}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-400 font-mono">
                    {crew.role.replace('_', ' ')} · Base: <strong className="text-white">{crew.home_base}</strong>
                  </div>
                </div>

                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                    crew.is_active
                      ? 'bg-emerald-950/70 text-emerald-400 border border-emerald-800/60'
                      : 'bg-rose-950/70 text-rose-400 border border-rose-800/60'
                  }`}
                >
                  {crew.is_active ? 'ACTIVE' : 'INACTIVE'}
                </span>
              </div>

              {/* Station & Location */}
              <div className="flex items-center justify-between text-xs font-mono p-2 rounded bg-slate-950/80 border border-slate-800/80">
                <span className="text-slate-400">Current Station:</span>
                <span className="font-bold text-cyan-300">{crew.current_location || crew.home_base}</span>
              </div>

              {/* Type Ratings & Qualifications */}
              <div className="space-y-1 text-xs">
                <div className="text-[10px] text-slate-400 uppercase font-mono">Type Ratings:</div>
                <div className="flex flex-wrap gap-1.5">
                  {crew.qualifications.map((q: any, idx: number) => {
                    const expired = isExpired(q.valid_until_utc);
                    return (
                      <span
                        key={idx}
                        className={`px-2 py-0.5 rounded text-[10px] font-mono border flex items-center gap-1 ${
                          expired
                            ? 'bg-rose-950/40 text-rose-400 border-rose-800/60'
                            : 'bg-cyan-950/40 text-cyan-300 border-cyan-800/60'
                        }`}
                      >
                        <Award className="w-3 h-3" />
                        <span>{q.aircraft_type}</span>
                        {expired && <span className="font-bold">(EXPIRED)</span>}
                      </span>
                    );
                  })}
                  {crew.qualifications.length === 0 && (
                    <span className="text-[11px] text-slate-500 italic">No type rating recorded</span>
                  )}
                </div>
              </div>

              {/* 7-Day Cumulative Meters */}
              <div className="space-y-2 pt-1 font-mono text-xs">
                <div>
                  <div className="flex items-center justify-between text-[10px] text-slate-400 mb-0.5">
                    <span>7-Day Flight Time ({flightHours.toFixed(1)}h / {maxFlight}h)</span>
                    <span className={flightPct > 85 ? 'text-amber-400 font-bold' : 'text-slate-400'}>{flightPct}%</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-950 rounded-full overflow-hidden border border-slate-800">
                    <div
                      className={`h-full rounded-full ${flightPct > 85 ? 'bg-amber-400' : 'bg-cyan-500'}`}
                      style={{ width: `${flightPct}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between text-[10px] text-slate-400 mb-0.5">
                    <span>7-Day Duty Period ({dutyHours.toFixed(1)}h / {maxDuty}h)</span>
                    <span className={dutyPct > 85 ? 'text-amber-400 font-bold' : 'text-slate-400'}>{dutyPct}%</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-950 rounded-full overflow-hidden border border-slate-800">
                    <div
                      className={`h-full rounded-full ${dutyPct > 85 ? 'bg-amber-400' : 'bg-emerald-500'}`}
                      style={{ width: `${dutyPct}%` }}
                    />
                  </div>
                </div>
              </div>

              {/* Card Footer: View Schedule Modal */}
              <div className="pt-2 border-t border-slate-200 dark:border-slate-800 flex justify-end">
                <button
                  onClick={() => handleOpenSchedule(crew)}
                  className="px-2.5 py-1 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-medium transition flex items-center gap-1.5 shadow-2xs"
                >
                  <Calendar className="w-3.5 h-3.5 text-sky-600 dark:text-cyan-400" />
                  <span>Inspect Duty Intervals</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Crew Duty Schedule Modal */}
      {selectedCrew && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-cyan-400" />
                <h3 className="text-sm font-semibold text-white">
                  RBIntervalTree Duty Timeline: {selectedCrew.name} ({selectedCrew.id})
                </h3>
              </div>
              <button
                onClick={() => setSelectedCrew(null)}
                className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 font-mono text-xs">
              <div className="p-2.5 rounded bg-slate-950 border border-slate-800 text-[11px] space-y-1">
                <div>Role: <strong className="text-white">{selectedCrew.role}</strong> | Base: <strong className="text-cyan-400">{selectedCrew.home_base}</strong></div>
                <div className="text-slate-400">
                  Data structure: <code className="text-cyan-300">RBIntervalTree</code> keyed by <code className="text-cyan-300">[report_utc, release_utc)</code>
                </div>
              </div>

              {isLoadingSchedule ? (
                <div className="py-8 text-center text-slate-400">Loading duty periods from index...</div>
              ) : dutySchedule.length === 0 ? (
                <div className="py-8 text-center text-slate-500 italic">
                  No active duty intervals recorded for this crew member in RBIntervalTree.
                </div>
              ) : (
                <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                  {dutySchedule.map((duty, idx) => (
                    <div key={idx} className="p-2.5 rounded bg-slate-950 border border-slate-800/80 space-y-1">
                      <div className="flex items-center justify-between text-cyan-300 font-bold">
                        <span>{duty.duty_id}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                          {duty.duty_type}
                        </span>
                      </div>
                      <div className="text-slate-300 text-[11px]">
                        Report: {formatUtcTime(duty.report_utc)} → Release: {formatUtcTime(duty.release_utc)}
                      </div>
                      <div className="text-[10px] text-slate-400">
                        Legs: {duty.flight_numbers.join(', ')}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="flex justify-end pt-2 border-t border-slate-800">
              <button
                onClick={() => setSelectedCrew(null)}
                className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 hover:text-white text-xs font-semibold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
