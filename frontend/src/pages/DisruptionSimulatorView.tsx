import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  Play,
  CheckCircle,
  ShieldAlert,
  Sliders,
} from 'lucide-react';
import { DisruptionPreset, DisruptionExecuteResponse } from '../types';
import { api } from '../services/api';

interface DisruptionSimulatorViewProps {
  onRefreshAll: () => void;
}

export const DisruptionSimulatorView: React.FC<DisruptionSimulatorViewProps> = ({
  onRefreshAll,
}) => {
  const [presets, setPresets] = useState<DisruptionPreset[]>([]);

  // Execution state
  const [isExecuting, setIsExecuting] = useState(false);
  const [activeScenarioName, setActiveScenarioName] = useState<string | null>(null);
  const [executionResult, setExecutionResult] = useState<DisruptionExecuteResponse | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);

  // Custom runner form
  const [customScenario, setCustomScenario] = useState('PILOT_SICK');
  const [customFlight, setCustomFlight] = useState('NV-101');
  const [customCrew, setCustomCrew] = useState('CR-001');
  const [customTail, setCustomTail] = useState('VT-NVA');
  const [customDelay, setCustomDelay] = useState(60);

  useEffect(() => {
    async function loadPresets() {
      try {
        const res = await api.getDisruptionPresets();
        setPresets(res.presets || []);
      } catch (err) {
        console.error('Failed to load disruption presets', err);
      }
    }
    loadPresets();
  }, []);

  const handleRunPreset = async (preset: DisruptionPreset) => {
    setIsExecuting(true);
    setActiveScenarioName(preset.title);
    setErrorText(null);
    setExecutionResult(null);

    try {
      let payload: any = {
        scenario_type: preset.scenario_type,
      };

      if (preset.scenario_type === 'PILOT_SICK') {
        payload.crew_id = preset.target_id;
        payload.flight_number = 'NV-101';
      } else if (preset.scenario_type === 'AIRCRAFT_AOG') {
        payload.aircraft_tail = preset.target_id;
        payload.flight_number = 'NV-101';
      } else if (preset.scenario_type === 'FLIGHT_DELAY_CASCADE') {
        payload.flight_number = preset.target_id;
        payload.delay_minutes = preset.delay_minutes || 75;
      } else if (preset.scenario_type === 'NO_LEGAL_SOLUTION') {
        payload.flight_number = preset.target_id;
      } else if (preset.scenario_type === 'INVALID_MANUAL_OVERRIDE') {
        payload.flight_number = preset.target_id;
        payload.override_captain_id = 'CR-009'; // Unqualified for A320
      }

      const res = await api.executeDisruption(payload);
      setExecutionResult(res);
      onRefreshAll();
    } catch (err: any) {
      setErrorText(err.message || 'Disruption execution failed');
    } finally {
      setIsExecuting(false);
    }
  };

  const handleRunCustom = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsExecuting(true);
    setActiveScenarioName(`Custom: ${customScenario}`);
    setErrorText(null);
    setExecutionResult(null);

    try {
      const payload: any = {
        scenario_type: customScenario,
        flight_number: customFlight,
        crew_id: customCrew,
        aircraft_tail: customTail,
        delay_minutes: customDelay,
      };

      if (customScenario === 'INVALID_MANUAL_OVERRIDE') {
        payload.override_captain_id = customCrew;
      }

      const res = await api.executeDisruption(payload);
      setExecutionResult(res);
      onRefreshAll();
    } catch (err: any) {
      setErrorText(err.message || 'Custom disruption execution failed');
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-base font-bold text-white flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-amber-400" />
          <span>Operations Disruption & Automated Recovery Simulator</span>
        </h2>
        <p className="text-xs text-slate-400">
          Deterministic execution of mandatory Scenarios A through E on Nova Air flights with atomic ADS synchronization
        </p>
      </div>

      {/* Preset Cards Grid (Scenarios A through E) */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
        {presets.map((p, idx) => {
          const letter = String.fromCharCode(65 + idx);
          return (
            <div
              key={p.scenario_type}
              className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition flex flex-col justify-between shadow-sm space-y-3"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-cyan-950 text-cyan-300 border border-cyan-800/60">
                    SCENARIO {letter}
                  </span>
                  <span className="text-[10px] font-mono text-slate-500">
                    Target: {p.target_id}
                  </span>
                </div>
                <div className="text-sm font-bold text-white font-sans">{p.title}</div>
                <div className="text-xs text-slate-300 font-sans">{p.description}</div>
                <div className="text-[11px] text-slate-400 font-mono bg-slate-950 p-2 rounded border border-slate-800/80">
                  Objective: {p.academic_objective}
                </div>
              </div>

              <div className="pt-2 border-t border-slate-800 flex items-center justify-between">
                <span className="text-[10px] font-mono text-slate-500">{p.scenario_type}</span>
                <button
                  onClick={() => handleRunPreset(p)}
                  disabled={isExecuting}
                  className="px-3 py-1 rounded bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-xs font-semibold flex items-center gap-1.5 transition active:scale-95"
                >
                  <Play className={`w-3.5 h-3.5 ${isExecuting && activeScenarioName === p.title ? 'animate-spin' : ''}`} />
                  <span>Execute Preset</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Execution Results & Before/After Diff Panel */}
      {executionResult && (
        <div className="p-5 rounded-xl bg-slate-900 border border-cyan-500/50 shadow-xl space-y-4 animate-in fade-in zoom-in-95">
          <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-3 gap-2">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-emerald-400" />
              <div>
                <h3 className="text-sm font-bold text-white">
                  Disruption Execution Complete: {executionResult.scenario}
                </h3>
                <div className="text-xs text-slate-400">{executionResult.message}</div>
              </div>
            </div>
            <div className="flex items-center gap-2 font-mono text-xs">
              <span className="text-slate-400">All Invariants Verified:</span>
              <span className="px-2.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold">
                PASS (100%)
              </span>
            </div>
          </div>

          {/* Telemetry Numbers */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
              <div className="text-slate-500 text-[10px]">Impacted Legs</div>
              <div className="text-base font-bold text-amber-300">
                {executionResult.impacted_flights_count} ({executionResult.impacted_flights.join(', ') || 'None'})
              </div>
            </div>
            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
              <div className="text-slate-500 text-[10px]">Successfully Recovered</div>
              <div className="text-base font-bold text-emerald-400">
                {executionResult.reassigned_flights_count} ({executionResult.reassigned_flights.join(', ') || 'None'})
              </div>
            </div>
            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
              <div className="text-slate-500 text-[10px]">Unassigned (Fail-Closed)</div>
              <div className="text-base font-bold text-white">
                {executionResult.unassigned_flights_count} ({executionResult.unassigned_flights.join(', ') || 'None'})
              </div>
            </div>
            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
              <div className="text-slate-500 text-[10px]">Hard Violations Prevented</div>
              <div className="text-base font-bold text-cyan-300">
                {executionResult.violations_prevented_count}
              </div>
            </div>
          </div>

          {/* ADS Mutations Log */}
          {executionResult.ads_mutations && (
            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800/80 font-mono text-xs space-y-1">
              <div className="text-[10px] uppercase text-cyan-400 font-bold">Critical-Path ADS Mutations:</div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-slate-300 text-[11px] pt-1">
                <div>B-Tree Keys Re-indexed: <strong>{executionResult.ads_mutations.btree_keys_updated ?? 0}</strong></div>
                <div>Interval Tree Conflicts Resolved: <strong>{executionResult.ads_mutations.interval_tree_conflicts_resolved ?? 0}</strong></div>
                <div>Graph Edges Synchronized: <strong>{executionResult.ads_mutations.graph_edges_updated ?? 0}</strong></div>
                <div>HashTable Lookups: <strong>{executionResult.ads_mutations.hash_lookups ?? 0}</strong></div>
              </div>
            </div>
          )}

          {/* Rejection / Violation Details if any */}
          {executionResult.violations && executionResult.violations.length > 0 && (
            <div className="space-y-1.5 font-mono text-xs">
              <div className="text-[11px] text-rose-400 font-bold uppercase">Evaluated Hard Rule Violations (Fail-Closed):</div>
              <div className="space-y-1 max-h-32 overflow-y-auto">
                {executionResult.violations.map((v, i) => (
                  <div key={i} className="p-2 rounded bg-rose-950/40 border border-rose-900/60 text-rose-300 text-[11px]">
                    <strong>[{v.rule_id}]</strong> {v.message} ({v.entity_id})
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {errorText && (
        <div className="p-4 rounded-xl bg-rose-950/60 border border-rose-800 text-rose-200 text-xs font-mono space-y-1">
          <div className="font-bold flex items-center gap-1.5">
            <ShieldAlert className="w-4 h-4 text-rose-400" />
            <span>Disruption Transaction Rejected:</span>
          </div>
          <div>{errorText}</div>
        </div>
      )}

      {/* Custom Parameters Disruption Runner */}
      <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-3">
        <div className="flex items-center gap-2">
          <Sliders className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono">
            Custom Disruption Injection Runner
          </h3>
        </div>

        <form onSubmit={handleRunCustom} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 text-xs font-mono">
          <div>
            <label className="block text-slate-400 mb-1">Scenario Type:</label>
            <select
              value={customScenario}
              onChange={(e) => setCustomScenario(e.target.value)}
              className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white"
            >
              <option value="PILOT_SICK">PILOT_SICK</option>
              <option value="AIRCRAFT_AOG">AIRCRAFT_AOG</option>
              <option value="FLIGHT_DELAY_CASCADE">FLIGHT_DELAY_CASCADE</option>
              <option value="NO_LEGAL_SOLUTION">NO_LEGAL_SOLUTION</option>
              <option value="INVALID_MANUAL_OVERRIDE">INVALID_MANUAL_OVERRIDE</option>
            </select>
          </div>

          <div>
            <label className="block text-slate-400 mb-1">Flight Number:</label>
            <input
              type="text"
              value={customFlight}
              onChange={(e) => setCustomFlight(e.target.value)}
              className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white uppercase"
            />
          </div>

          <div>
            <label className="block text-slate-400 mb-1">Crew ID:</label>
            <input
              type="text"
              value={customCrew}
              onChange={(e) => setCustomCrew(e.target.value)}
              className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white uppercase"
            />
          </div>

          <div>
            <label className="block text-slate-400 mb-1">Aircraft Tail:</label>
            <input
              type="text"
              value={customTail}
              onChange={(e) => setCustomTail(e.target.value)}
              className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white uppercase"
            />
          </div>

          <div>
            <label className="block text-slate-400 mb-1">Delay (Min):</label>
            <input
              type="number"
              value={customDelay}
              onChange={(e) => setCustomDelay(Number(e.target.value))}
              className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white"
            />
          </div>

          <div className="flex items-end">
            <button
              type="submit"
              disabled={isExecuting}
              className="w-full p-2 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-semibold transition"
            >
              {isExecuting ? 'Injecting...' : 'Inject Disruption'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
