import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  BookOpen,
  Info,
  Scale,
  Search,
} from 'lucide-react';
import { RuleInspectorResponse } from '../types';
import { api } from '../services/api';

export const ConstraintInspectorView: React.FC = () => {
  const [inspectorData, setInspectorData] = useState<RuleInspectorResponse | null>(null);
  const [selectedClass, setSelectedClass] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    async function loadInspector() {
      try {
        const data = await api.getConstraintsInspector();
        setInspectorData(data);
      } catch (err) {
        console.error('Failed to load constraints inspector', err);
      }
    }
    loadInspector();
  }, []);

  const classifications = ['ALL', 'STATUTORY_DGCA_BASELINE', 'OPERATOR_POLICY', 'DEMO_ASSUMPTION'];

  const hardRules = [
    {
      id: 'CREW-ROLE-01',
      title: 'Role Separation & Crew Complement',
      mechanism: 'SeparateChainingHashTable & Domain Validation',
      desc: 'Captain must hold CAPTAIN role; First Officer must hold FIRST_OFFICER. No duplicate crew within pairing.',
    },
    {
      id: 'CREW-QUAL-01',
      title: 'Aircraft Type Qualification',
      mechanism: 'CrewMember.qualifications check',
      desc: 'Crew must hold active type rating matching the flight equipment (A320 or ATR72).',
    },
    {
      id: 'CREW-EXP-01',
      title: 'Type Rating Expiration',
      mechanism: 'Epoch UTC comparison (valid_until_utc >= arr_utc)',
      desc: 'Rating expiration timestamp must not precede scheduled flight arrival timestamp.',
    },
    {
      id: 'CREW-OVLP-01',
      title: 'Duty Interval Non-Overlap',
      mechanism: 'RBIntervalTree.find_first_overlap',
      desc: 'Half-open [report_utc, release_utc) duty interval must not overlap any existing duty, standby, or positioning window.',
    },
    {
      id: 'CREW-REST-01',
      title: 'Inter-Duty Minimum Rest',
      mechanism: 'RBIntervalTree.find_predecessor & find_successor',
      desc: 'Mandatory rest gap >= max(12 hours, duration of preceding duty period) before subsequent report time.',
    },
    {
      id: 'CREW-FDP-01',
      title: 'Maximum Daily Flight Duty Period',
      mechanism: 'Rule Profile cumulative duty calculation',
      desc: 'FDP duration from first report to final release must not exceed sector-dependent limit (Flight Crew: 12.5h, Cabin: 13h).',
    },
    {
      id: 'CREW-FT-01',
      title: 'Maximum Daily Flight Time',
      mechanism: 'Sum of airborne seconds within FDP',
      desc: 'Cumulative block flight time must not exceed daily ceiling (Flight Crew: 8h, Cabin: 10h).',
    },
    {
      id: 'CREW-CUM-01',
      title: '7-Day Rolling Limits',
      mechanism: 'Rolling cumulative flight (35h) & duty (60h) counters',
      desc: 'AirCrewOps enforces 7-day cumulative statutory caps informed by DGCA CAR Sec 7 Series J.',
    },
    {
      id: 'CREW-POS-01',
      title: 'Aerodrome Location & Positioning Feasibility',
      mechanism: 'FlightConnectionGraph.find_shortest_positioning_path (Dijkstra)',
      desc: 'Crew must either already be located at flight origin or have a time-feasible deadhead itinerary arriving before report.',
    },
    {
      id: 'ACFT-STAT-01',
      title: 'Aircraft Serviceability & Type Match',
      mechanism: 'Aircraft.is_active and aircraft_type match',
      desc: 'Aircraft tail must be active (not grounded/AOG) and equipment type must match flight specification.',
    },
    {
      id: 'ACFT-OVLP-01',
      title: 'Aircraft Flight & Maintenance Non-Overlap',
      mechanism: 'RBIntervalTree.find_first_overlap',
      desc: 'Aircraft half-open [dep_utc, arr_utc) flight interval must not overlap scheduled maintenance or existing flight legs.',
    },
    {
      id: 'ACFT-LOC-01',
      title: 'Aircraft Route Continuity',
      mechanism: 'RBIntervalTree.find_predecessor origin/destination match',
      desc: 'Aircraft must arrive at aerodrome before departing on the next leg (location continuity).',
    },
    {
      id: 'ACFT-SUCC-01',
      title: 'Minimum Turnaround Time (TAT)',
      mechanism: 'RBIntervalTree rest-gap evaluation',
      desc: 'Ground turnaround buffer must meet or exceed aircraft type minimum (A320: 45m, ATR72: 30m).',
    },
    {
      id: 'PAIR-COMP-01',
      title: 'Flight Crew & Cabin Complement Completeness',
      mechanism: 'Complement count verification',
      desc: 'Requires 1 CPT, 1 FO, and minimum cabin crew (A320: 4, ATR72: 2) with zero duplicate crew assignments.',
    },
  ];

  const filteredParams = (inspectorData?.parameters || []).filter((p) => {
    const matchesClass = selectedClass === 'ALL' || p.classification === selectedClass;
    const matchesSearch =
      !searchQuery ||
      p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.parameter_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.description.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesClass && matchesSearch;
  });

  return (
    <div className="space-y-6">
      {/* Header and Statutory Source */}
      <div className="p-4 rounded-xl bg-gradient-to-r from-slate-900 to-slate-950 border border-slate-800 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-cyan-600/20 text-cyan-400 border border-cyan-500/30">
              <Scale className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white flex items-center gap-2">
                <span>Civil Aviation Safety & Regulatory Rule Profile</span>
                <span className="text-xs px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 font-mono">
                  {inspectorData?.profile_id || 'nova_air_demo_v1'}
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Informed by statutory Indian DGCA CAR Section 7, Series J (Part III for Flight Crew, Part I for Cabin Crew)
              </p>
            </div>
          </div>

          <div className="px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-[11px] font-mono text-slate-400">
            Effective: <strong className="text-white">{inspectorData?.effective_date || '2026-06-01'}</strong>
          </div>
        </div>

        {/* Academic Mission Notice */}
        <div className="p-3 rounded-lg bg-amber-950/30 border border-amber-900/50 text-amber-300 text-xs flex items-start gap-2.5">
          <Info className="w-4 h-4 shrink-0 text-amber-400 mt-0.5" />
          <div>
            <strong>Educational Simulation Disclaimer:</strong> AirCrewOps is designed strictly for academic evaluation of custom Advanced Data Structures (ADS) at NMIMS MPSTME. It models DGCA CAR FDTL regulations for simulation and is not certified for commercial flight dispatch.
          </div>
        </div>
      </div>

      {/* Fail-Closed Hard Rules Checklist */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Fail-Closed Aviation Hard Rules (ConstraintEngine)</span>
          </h3>
          <span className="text-xs text-slate-400 font-mono">
            {hardRules.length} Verified Hard Rules · 0% Override Allowance
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {hardRules.map((rule) => (
            <div
              key={rule.id}
              className="p-3 rounded-xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition space-y-1.5"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-cyan-300 font-mono">{rule.id}</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-950/60 text-rose-400 border border-rose-800/60">
                  HARD FAIL-CLOSED
                </span>
              </div>
              <div className="text-xs font-semibold text-white">{rule.title}</div>
              <div className="text-[11px] text-slate-400">{rule.desc}</div>
              <div className="text-[10px] font-mono text-slate-500 pt-1 border-t border-slate-800/80">
                Evaluation: <span className="text-slate-300">{rule.mechanism}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Configurable Regulatory Parameters Table */}
      <div className="space-y-3 pt-2">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-cyan-400" />
            <span>Profile Parameter Register ({filteredParams.length} parameters)</span>
          </h3>

          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-[160px]">
              <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                placeholder="Filter parameters..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
              />
            </div>

            <div className="flex items-center gap-1 text-xs">
              {classifications.map((cls) => (
                <button
                  key={cls}
                  onClick={() => setSelectedClass(cls)}
                  className={`px-2 py-1 rounded text-[11px] font-mono transition ${
                    selectedClass === cls
                      ? 'bg-cyan-600 text-white font-bold'
                      : 'bg-slate-900 border border-slate-800 text-slate-400 hover:text-white'
                  }`}
                >
                  {cls.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/80 overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/90 text-slate-400 border-b border-slate-800 uppercase text-[10px] font-mono">
                <tr>
                  <th className="py-2.5 px-3">Parameter ID</th>
                  <th className="py-2.5 px-3">Name & Description</th>
                  <th className="py-2.5 px-3">Configured Value</th>
                  <th className="py-2.5 px-3">Classification</th>
                  <th className="py-2.5 px-3">Statutory Citation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {filteredParams.map((param) => {
                  const isStatutory = param.classification === 'STATUTORY_DGCA_BASELINE';
                  return (
                    <tr key={param.parameter_id} className="hover:bg-slate-800/40 transition">
                      <td className="py-2.5 px-3 font-bold text-cyan-300">
                        {param.parameter_id}
                      </td>
                      <td className="py-2.5 px-3 font-sans">
                        <div className="font-semibold text-white">{param.name}</div>
                        <div className="text-[11px] text-slate-400">{param.description}</div>
                      </td>
                      <td className="py-2.5 px-3 text-white font-bold">
                        {typeof param.value === 'object' ? JSON.stringify(param.value) : String(param.value)}{' '}
                        <span className="text-[10px] text-slate-500 font-normal">{param.unit}</span>
                      </td>
                      <td className="py-2.5 px-3">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                            isStatutory
                              ? 'bg-cyan-950/70 text-cyan-300 border-cyan-800/60'
                              : 'bg-slate-800 text-slate-300 border-slate-700'
                          }`}
                        >
                          {param.classification}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-[11px] text-slate-400 font-sans">
                        {param.citation}
                      </td>
                    </tr>
                  );
                })}
                {filteredParams.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-6 text-center text-slate-500 italic">
                      No parameters matching filter criteria.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
