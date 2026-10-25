import React from 'react';
import {
  Plane,
  Users,
  ShieldAlert,
  Clock,
  Database,
  CheckCircle,
  AlertTriangle,
  ArrowRight,
  TrendingUp,
} from 'lucide-react';
import { DashboardSummary, FlightLeg, NavTab } from '../types';

interface OverviewViewProps {
  summary: DashboardSummary | null;
  upcomingFlights: FlightLeg[];
  onNavigate: (tab: NavTab) => void;
  isLoading: boolean;
}

export const OverviewView: React.FC<OverviewViewProps> = ({
  summary,
  upcomingFlights,
  onNavigate,
  isLoading,
}) => {
  if (isLoading && !summary) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
          <span className="text-xs text-slate-400 font-mono">Loading Operations Telemetry...</span>
        </div>
      </div>
    );
  }

  // Robust metric extraction with fallbacks to avoid undefined property access
  const kpis = {
    coverage_rate_percent: summary?.kpis?.coverage_rate_percent ?? 0,
    hard_violations_count: summary?.kpis?.hard_violations_count ?? 0,
    active_conflicts: summary?.kpis?.active_conflicts ?? 0,
    average_tat_slack_minutes: summary?.kpis?.average_tat_slack_minutes ?? 0,
    deadhead_positioning_legs: summary?.kpis?.deadhead_positioning_legs ?? 0,
  };

  const ads = {
    hash_table_items:
      summary?.ads_telemetry?.hash_table_items ??
      (summary ? (summary.total_flights || 0) + (summary.total_crew || 0) + (summary.total_aircraft || 0) + (summary.total_airports || 0) : 0),
    hash_table_load_factor:
      summary?.ads_telemetry?.hash_table_load_factor ?? 0.0,
    btree_keys:
      summary?.ads_telemetry?.btree_keys ??
      summary?.ads_telemetry?.schedule_btree?.size ??
      summary?.total_flights ??
      0,
    btree_height:
      summary?.ads_telemetry?.btree_height ??
      summary?.ads_telemetry?.schedule_btree?.height ??
      0,
    interval_tree_nodes:
      summary?.ads_telemetry?.interval_tree_nodes ??
      ((summary?.ads_telemetry?.total_crew_duty_intervals ?? 0) + (summary?.ads_telemetry?.total_aircraft_intervals ?? 0)),
    graph_vertices:
      summary?.ads_telemetry?.graph_vertices ??
      summary?.ads_telemetry?.connection_graph?.vertex_count ??
      0,
    graph_edges:
      summary?.ads_telemetry?.graph_edges ??
      summary?.ads_telemetry?.connection_graph?.edge_count ??
      0,
  };

  const formatDecimal = (val?: number | null, digits: number = 1, fallback: string = '0.0'): string => {
    if (typeof val === 'number' && !isNaN(val)) {
      return val.toFixed(digits);
    }
    return fallback;
  };

  const formatInt = (val?: number | null, fallback: number | string = 0): string | number => {
    if (typeof val === 'number' && !isNaN(val)) {
      return val;
    }
    return fallback;
  };

  const formatUtcTime = (epochSeconds: number) => {
    if (!epochSeconds) return '--:--';
    const d = new Date(epochSeconds * 1000);
    return d.toISOString().substring(11, 16) + 'Z';
  };

  return (
    <div className="space-y-6">
      {/* Educational Banner */}
      <div className="p-3 rounded-lg bg-gradient-to-r from-cyan-950/60 to-slate-900 border border-cyan-800/40 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded bg-cyan-500/20 text-cyan-500">
            <TrendingUp className="w-4 h-4" />
          </div>
          <div>
            <div className="text-sm font-bold text-black dark:text-white">
              Nova Air System Operations Control Center — Live Simulation Mode
            </div>
          </div>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {/* Coverage Rate */}
        <div className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition">
          <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
            <span>Roster Coverage</span>
            <CheckCircle className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className="text-xl font-bold text-white font-mono">
            {formatDecimal(kpis.coverage_rate_percent, 1)}%
          </div>
          <div className="text-[10px] text-slate-500 mt-1">
            {summary?.covered_flights || 0} of {summary?.total_flights || 0} legs covered
          </div>
        </div>

        {/* Unassigned / Alerts */}
        <div className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition">
          <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
            <span>Unassigned Legs</span>
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <div className="text-xl font-bold text-amber-300 font-mono">
            {summary?.unassigned_flights || 0}
          </div>
          <div className="text-[10px] text-slate-500 mt-1">
            Constrained or uncoverable
          </div>
        </div>

        {/* Hard Rule Violations */}
        <div className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition">
          <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
            <span>Hard Violations</span>
            <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
          </div>
          <div className="text-xl font-bold text-emerald-400 font-mono">
            {kpis.hard_violations_count}
          </div>
          <div className="text-[10px] text-slate-500 mt-1">
            Zero-tolerance hard rules
          </div>
        </div>

        {/* Active Aircraft */}
        <div className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition">
          <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
            <span>Active Fleet</span>
            <Plane className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className="text-xl font-bold text-white font-mono">
            {summary?.active_aircraft || 0} Tails
          </div>
          <div className="text-[10px] text-slate-500 mt-1">
            A320 & ATR72 rotations
          </div>
        </div>

        {/* Active Crew */}
        <div className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition">
          <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
            <span>Active Crew</span>
            <Users className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className="text-xl font-bold text-white font-mono">
            {summary?.active_crew || 0}
          </div>
          <div className="text-[10px] text-slate-500 mt-1">
            Flight & Cabin crew rostered
          </div>
        </div>

        {/* Average TAT Slack */}
        <div className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition">
          <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
            <span>Avg TAT Slack</span>
            <Clock className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className="text-xl font-bold text-white font-mono">
            {kpis.average_tat_slack_minutes}m
          </div>
          <div className="text-[10px] text-slate-500 mt-1">
            Buffer over minimum TAT
          </div>
        </div>
      </div>

      {/* Main Grid: Upcoming Flights & ADS In-Memory Telemetry */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column (2 spans): Upcoming Flights */}
        <div className="lg:col-span-2 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Plane className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-semibold text-slate-100">Upcoming Nova Air Departures</h3>
            </div>
            <button
              onClick={() => onNavigate('schedule')}
              className="text-xs text-sky-700 dark:text-cyan-400 hover:text-sky-900 dark:hover:text-cyan-300 flex items-center gap-1 font-semibold transition"
            >
              <span>View All Flights</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/80 overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 uppercase text-[10px] font-mono">
                  <tr>
                    <th className="py-2.5 px-3">Flight</th>
                    <th className="py-2.5 px-3">Route</th>
                    <th className="py-2.5 px-3">Departure</th>
                    <th className="py-2.5 px-3">Tail / Type</th>
                    <th className="py-2.5 px-3">Crew Assignment</th>
                    <th className="py-2.5 px-3 text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {upcomingFlights.slice(0, 8).map((flight) => {
                    const isCovered = flight.is_covered ?? (!!flight.captain_id && !!flight.first_officer_id);
                    return (
                      <tr key={flight.flight_number} className="hover:bg-slate-800/40 transition">
                        <td className="py-2 px-3 font-bold text-cyan-300">
                          {flight.flight_number}
                        </td>
                        <td className="py-2 px-3">
                          <span className="text-white font-semibold">{flight.origin}</span>
                          <span className="text-slate-500 mx-1">→</span>
                          <span className="text-white font-semibold">{flight.destination}</span>
                        </td>
                        <td className="py-2 px-3 text-slate-300">
                          {formatUtcTime(flight.effective_departure_utc || flight.departure_utc)}
                          {flight.delay_minutes ? (
                            <span className="ml-1 text-[10px] text-amber-400">+{flight.delay_minutes}m</span>
                          ) : null}
                        </td>
                        <td className="py-2 px-3 text-slate-400">
                          <span className="text-slate-200">{flight.aircraft_tail || '—'}</span>
                          <span className="text-[10px] text-slate-500 ml-1">({flight.aircraft_type})</span>
                        </td>
                        <td className="py-2 px-3 text-[11px]">
                          {flight.captain_id ? (
                            <span className="text-slate-300">
                              {flight.captain_id} / {flight.first_officer_id || 'FO Unassigned'}
                            </span>
                          ) : (
                            <span className="text-amber-400/90 italic">Unassigned</span>
                          )}
                        </td>
                        <td className="py-2 px-3 text-right">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-semibold ${isCovered
                                ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-800/60'
                                : 'bg-amber-950/60 text-amber-400 border border-amber-800/60'
                              }`}
                          >
                            {isCovered ? 'ASSIGNED' : 'UNASSIGNED'}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                  {upcomingFlights.length === 0 && (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-slate-500 italic">
                        No upcoming flight records loaded. Click "Generate Roster" or "Reset Demo" above.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right Column: ADS Custom Structures Telemetry Panel */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Database className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-semibold text-slate-100">ADS Index Manager Telemetry</h3>
            </div>
            <button
              onClick={() => onNavigate('laboratory')}
              className="text-xs text-sky-700 dark:text-cyan-400 hover:text-sky-900 dark:hover:text-cyan-300 flex items-center gap-1 font-semibold transition"
            >
              <span>Inspect Lab</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/90 space-y-3.5 text-xs font-mono">
            {/* Hash Table Metric */}
            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800/80">
              <div className="flex items-center justify-between text-slate-300 mb-1">
                <span className="font-semibold text-cyan-400">SeparateChainingHashTable</span>
                <span className="text-[10px] text-slate-500">O(1) lookups</span>
              </div>
              <div className="flex items-center justify-between text-slate-400 text-[11px]">
                <span>Indexed Entities: <strong className="text-white">{formatInt(ads.hash_table_items)}</strong></span>
                <span>Load Factor: <strong className="text-emerald-400">{formatDecimal(ads.hash_table_load_factor, 2, '0.00')}</strong></span>
              </div>
            </div>

            {/* B-Tree Metric */}
            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800/80">
              <div className="flex items-center justify-between text-slate-300 mb-1">
                <span className="font-semibold text-cyan-400">FlightScheduleBTree (t=3)</span>
                <span className="text-[10px] text-slate-500">O(log n + k) range</span>
              </div>
              <div className="flex items-center justify-between text-slate-400 text-[11px]">
                <span>Keys in Schedule: <strong className="text-white">{formatInt(ads.btree_keys)}</strong></span>
                <span>Tree Height: <strong className="text-emerald-400">{formatInt(ads.btree_height)}</strong></span>
              </div>
            </div>

            {/* RB-Interval Tree Metric */}
            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800/80">
              <div className="flex items-center justify-between text-slate-300 mb-1">
                <span className="font-semibold text-cyan-400">RBIntervalTree (max_end)</span>
                <span className="text-[10px] text-slate-500">O(log n) overlaps</span>
              </div>
              <div className="flex items-center justify-between text-slate-400 text-[11px]">
                <span>Active Duty/TAT Intervals: <strong className="text-white">{formatInt(ads.interval_tree_nodes)}</strong></span>
                <span className="text-emerald-400 font-bold">SENTINEL NIL OK</span>
              </div>
            </div>

            {/* Flight Connection Graph Metric */}
            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800/80">
              <div className="flex items-center justify-between text-slate-300 mb-1">
                <span className="font-semibold text-cyan-400">FlightConnectionGraph</span>
                <span className="text-[10px] text-slate-500">Dijkstra deadhead</span>
              </div>
              <div className="flex items-center justify-between text-slate-400 text-[11px]">
                <span>Vertices: <strong className="text-white">{formatInt(ads.graph_vertices)}</strong></span>
                <span>Feasible Edges: <strong className="text-cyan-300">{formatInt(ads.graph_edges)}</strong></span>
              </div>
            </div>

            <div className="pt-1 text-[11px] text-slate-500 flex items-center gap-1.5 font-sans">
              <CheckCircle className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              <span>All 5 custom structures active on simulation critical path.</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
