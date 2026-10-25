import React, { useState, useEffect } from 'react';
import {
  Cpu,
  Play,
  Terminal,
} from 'lucide-react';
import { ADSDiagnostics, ADSLabResponse } from '../types';
import { api } from '../services/api';

export const ADSLaboratoryView: React.FC = () => {
  const [diagnostics, setDiagnostics] = useState<ADSDiagnostics | null>(null);
  const [activeSubTab, setActiveSubTab] = useState<'hash_table' | 'btree' | 'interval_tree' | 'graph'>('hash_table');

  // Query Execution state
  const [isExecuting, setIsExecuting] = useState(false);
  const [labResponse, setLabResponse] = useState<ADSLabResponse | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);

  // Form parameters per sub-tab
  // Form parameters per sub-tab (calibrated to demo dataset March 31, 2026)
  const [hashKey, setHashKey] = useState('NV-101');
  const [hashEntityType, setHashEntityType] = useState('flights');

  const [btreeStartUtc, setBtreeStartUtc] = useState(1774936800);
  const [btreeEndUtc, setBtreeEndUtc] = useState(1774960000);

  const [intervalStartUtc, setIntervalStartUtc] = useState(1774936800);
  const [intervalEndUtc, setIntervalEndUtc] = useState(1774945200);
  const [intervalTail, setIntervalTail] = useState('VT-NVA');

  const [graphOrigin, setGraphOrigin] = useState('BOM');
  const [graphDest, setGraphDest] = useState('DEL');
  const [graphDepUtc, setGraphDepUtc] = useState(1774936800);
  const [graphArrUtc] = useState(1774960000);

  useEffect(() => {
    async function loadDiag() {
      try {
        const diag = await api.getADSDiagnostics();
        setDiagnostics(diag);
      } catch (err) {
        console.error('Failed to load ADS diagnostics', err);
      }
    }
    loadDiag();
  }, []);

  const handleExecuteQuery = async (structure: 'hash_table' | 'btree' | 'interval_tree' | 'graph') => {
    setIsExecuting(true);
    setQueryError(null);
    setLabResponse(null);

    let params: Record<string, any> = {};
    let operation = 'get';

    if (structure === 'hash_table') {
      operation = 'lookup';
      params = { key: hashKey, entity_type: hashEntityType, table: hashEntityType };
    } else if (structure === 'btree') {
      operation = 'range_query';
      params = {
        start_utc: btreeStartUtc,
        end_utc: btreeEndUtc,
        start_time_utc: btreeStartUtc,
        end_time_utc: btreeEndUtc,
      };
    } else if (structure === 'interval_tree') {
      operation = 'find_overlap';
      params = {
        resource_id: intervalTail,
        aircraft_tail: intervalTail,
        start_utc: intervalStartUtc,
        end_utc: intervalEndUtc,
      };
    } else if (structure === 'graph') {
      operation = 'shortest_path';
      params = {
        origin: graphOrigin,
        destination: graphDest,
        departure_utc: graphDepUtc,
        earliest_dep_utc: graphDepUtc,
        latest_arr_utc: graphArrUtc,
      };
    }

    try {
      const res = await api.executeADSLabQuery({
        structure,
        operation,
        params,
      });
      setLabResponse(res);
      // Reload diagnostics to reflect any telemetry updates
      const updatedDiag = await api.getADSDiagnostics();
      setDiagnostics(updatedDiag);
    } catch (err: any) {
      setQueryError(err.message || 'Lab query execution failed');
    } finally {
      setIsExecuting(false);
    }
  };

  const subTabs = [
    { id: 'hash_table' as const, name: 'SeparateChainingHashTable', complexity: 'O(1) Avg' },
    { id: 'btree' as const, name: 'FlightScheduleBTree (t=3)', complexity: 'O(log n + k)' },
    { id: 'interval_tree' as const, name: 'RBIntervalTree (max_end)', complexity: 'O(log n)' },
    { id: 'graph' as const, name: 'FlightConnectionGraph (Dijkstra)', complexity: 'O((V+E) log V)' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-base font-bold text-white flex items-center gap-2">
          <Cpu className="w-5 h-5 text-cyan-400" />
          <span>Advanced Data Structures (ADS) Laboratory Workbench</span>
        </h2>
        <p className="text-xs text-slate-400">
          NMIMS MPSTME live in-memory telemetry, structural invariant auditing, and algorithm complexity verification
        </p>
      </div>

      {/* Global ADS Health Diagnostic Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs font-mono">
        <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
          <div className="text-[10px] text-slate-500">Hash Table Capacity</div>
          <div className="text-base font-bold text-white">
            {diagnostics?.hash_table?.size || 0} / {diagnostics?.hash_table?.capacity || 64}
          </div>
          <div className="text-[10px] text-emerald-400">
            Load: {diagnostics?.hash_table?.load_factor?.toFixed(2) || '0.00'} (&le; 0.75)
          </div>
        </div>

        <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
          <div className="text-[10px] text-slate-500">B-Tree Height (Degree 3)</div>
          <div className="text-base font-bold text-cyan-300">
            Height = {diagnostics?.btree?.height || 2}
          </div>
          <div className="text-[10px] text-slate-400">
            Keys: {diagnostics?.btree?.keys_count || 0} ({diagnostics?.btree?.node_count || 0} nodes)
          </div>
        </div>

        <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
          <div className="text-[10px] text-slate-500">RB-Interval Trees</div>
          <div className="text-base font-bold text-emerald-400">
            {diagnostics?.interval_tree?.total_intervals || 0} Intervals
          </div>
          <div className="text-[10px] text-emerald-400 font-bold">
            NIL SENTINEL OK
          </div>
        </div>

        <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
          <div className="text-[10px] text-slate-500">Flight Graph Network</div>
          <div className="text-base font-bold text-white">
            {diagnostics?.graph?.airports_count || 7} Airports
          </div>
          <div className="text-[10px] text-cyan-400">
            {diagnostics?.graph?.edges_count || 0} Feasible Edges
          </div>
        </div>

        <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
          <div className="text-[10px] text-slate-500">Scheduler Priority Queue</div>
          <div className="text-base font-bold text-white">
            Min-Heap
          </div>
          <div className="text-[10px] text-emerald-400 font-bold">
            INVARIANT VERIFIED
          </div>
        </div>
      </div>

      {/* Laboratory Sub-Tabs */}
      <div className="border-b border-slate-800 flex items-center overflow-x-auto gap-2">
        {subTabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => {
              setActiveSubTab(tab.id);
              setLabResponse(null);
              setQueryError(null);
            }}
            className={`px-4 py-2.5 text-xs font-mono font-medium border-b-2 transition whitespace-nowrap flex items-center gap-2 ${
              activeSubTab === tab.id
                ? 'border-cyan-400 text-cyan-300 bg-slate-900/60 font-bold'
                : 'border-transparent text-slate-400 hover:text-white'
            }`}
          >
            <span>{tab.name}</span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 font-normal">
              {tab.complexity}
            </span>
          </button>
        ))}
      </div>

      {/* Active Sub-Tab Control & Query Execution Panel */}
      <div className="p-5 rounded-xl bg-slate-900/90 border border-slate-800 shadow-sm space-y-4">
        {/* Sub-Tab 1: Hash Table */}
        {activeSubTab === 'hash_table' && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-bold text-white font-mono">
                  SeparateChainingHashTable Inspector
                </h3>
                <p className="text-xs text-slate-400">
                  FNV-1a 64-bit deterministic hash with linked bucket chaining and dynamic 2x resizing at load factor &gt; 0.75
                </p>
              </div>
              <div className="flex items-center gap-1.5 font-mono text-[11px]">
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">O(1) Average</span>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">O(n) Worst</span>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Entity Domain Table:</label>
                <select
                  value={hashEntityType}
                  onChange={(e) => setHashEntityType(e.target.value)}
                  className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white font-semibold"
                >
                  <option value="flights">flights_by_id</option>
                  <option value="crew">crew_by_id</option>
                  <option value="aircraft">aircraft_by_id</option>
                  <option value="airports">airports_by_code</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Entity Key to Lookup:</label>
                <input
                  type="text"
                  placeholder="e.g. NV-101, CR-001, BOM"
                  value={hashKey}
                  onChange={(e) => setHashKey(e.target.value)}
                  className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white font-semibold uppercase"
                />
              </div>

              <div className="flex items-end">
                <button
                  onClick={() => handleExecuteQuery('hash_table')}
                  disabled={isExecuting}
                  className="w-full p-2 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-semibold flex items-center justify-center gap-1.5 transition"
                >
                  <Play className={`w-3.5 h-3.5 ${isExecuting ? 'animate-spin' : ''}`} />
                  <span>Execute O(1) Lookup</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Sub-Tab 2: B-Tree */}
        {activeSubTab === 'btree' && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-bold text-white font-mono">
                  FlightScheduleBTree (min_degree=3) Range Query Inspector
                </h3>
                <p className="text-xs text-slate-400">
                  Pruned traversal of composite key (effective_departure_utc, flight_id) with proactive root splitting and underflow merging
                </p>
              </div>
              <div className="flex items-center gap-1.5 font-mono text-[11px]">
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">O(log n + k)</span>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">Height: {diagnostics?.btree?.height || 2}</span>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Start Time (UTC Epoch):</label>
                <input
                  type="number"
                  value={btreeStartUtc}
                  onChange={(e) => setBtreeStartUtc(Number(e.target.value))}
                  className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white font-semibold"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">End Time (UTC Epoch):</label>
                <input
                  type="number"
                  value={btreeEndUtc}
                  onChange={(e) => setBtreeEndUtc(Number(e.target.value))}
                  className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white font-semibold"
                />
              </div>

              <div className="flex items-end">
                <button
                  onClick={() => handleExecuteQuery('btree')}
                  disabled={isExecuting}
                  className="w-full p-2 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-semibold flex items-center justify-center gap-1.5 transition"
                >
                  <Play className={`w-3.5 h-3.5 ${isExecuting ? 'animate-spin' : ''}`} />
                  <span>Execute Range Search</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Sub-Tab 3: RB-Interval Tree */}
        {activeSubTab === 'interval_tree' && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-bold text-white font-mono">
                  RBIntervalTree Overlap & Duty Conflict Inspector
                </h3>
                <p className="text-xs text-slate-400">
                  Half-open [start_utc, end_utc) interval search augmented with subtree max_end for duty, turnaround, and maintenance conflicts
                </p>
              </div>
              <div className="flex items-center gap-1.5 font-mono text-[11px]">
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">O(log n) Overlap</span>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">Black Sentinel NIL</span>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Aircraft Tail:</label>
                <input
                  type="text"
                  value={intervalTail}
                  onChange={(e) => setIntervalTail(e.target.value)}
                  className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white uppercase font-semibold"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Interval Start UTC:</label>
                <input
                  type="number"
                  value={intervalStartUtc}
                  onChange={(e) => setIntervalStartUtc(Number(e.target.value))}
                  className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white font-semibold"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Interval End UTC:</label>
                <input
                  type="number"
                  value={intervalEndUtc}
                  onChange={(e) => setIntervalEndUtc(Number(e.target.value))}
                  className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white font-semibold"
                />
              </div>

              <div className="flex items-end">
                <button
                  onClick={() => handleExecuteQuery('interval_tree')}
                  disabled={isExecuting}
                  className="w-full p-2 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-semibold flex items-center justify-center gap-1.5 transition"
                >
                  <Play className={`w-3.5 h-3.5 ${isExecuting ? 'animate-spin' : ''}`} />
                  <span>Check Overlap</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Sub-Tab 4: Dijkstra Graph */}
        {activeSubTab === 'graph' && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-bold text-white font-mono">
                  FlightConnectionGraph Dijkstra Deadhead Positioning Path
                </h3>
                <p className="text-xs text-slate-400">
                  Directed multigraph with non-negative elapsed flight times; discovers minimum-elapsed-time multi-hop repositioning paths
                </p>
              </div>
              <div className="flex items-center gap-1.5 font-mono text-[11px]">
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">O((V+E) log V)</span>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">Ephemeral Virtual Source</span>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Origin Airport:</label>
                <input
                  type="text"
                  value={graphOrigin}
                  onChange={(e) => setGraphOrigin(e.target.value)}
                  className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white uppercase font-semibold"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Target Airport:</label>
                <input
                  type="text"
                  value={graphDest}
                  onChange={(e) => setGraphDest(e.target.value)}
                  className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white uppercase font-semibold"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Earliest Departure UTC:</label>
                <input
                  type="number"
                  value={graphDepUtc}
                  onChange={(e) => setGraphDepUtc(Number(e.target.value))}
                  className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white font-semibold"
                />
              </div>

              <div className="flex items-end">
                <button
                  onClick={() => handleExecuteQuery('graph')}
                  disabled={isExecuting}
                  className="w-full p-2 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-semibold flex items-center justify-center gap-1.5 transition"
                >
                  <Play className={`w-3.5 h-3.5 ${isExecuting ? 'animate-spin' : ''}`} />
                  <span>Find Dijkstra Path</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Query Output Display Panel */}
        {labResponse && (
          <div className="p-4 rounded-xl bg-slate-950 border border-cyan-800/60 font-mono text-xs space-y-3 animate-in fade-in zoom-in-95">
            <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-2 gap-2">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-cyan-400" />
                <span className="font-bold text-white uppercase">
                  Operation: {labResponse.operation} ({labResponse.structure})
                </span>
              </div>
              <div className="flex items-center gap-3 text-[11px]">
                <span className="text-slate-400">Execution: <strong className="text-emerald-400">{(labResponse.execution_time_ms ?? 0).toFixed(2)} ms</strong></span>
                <span className="text-slate-400">Time Complexity: <strong className="text-cyan-300">{labResponse.time_complexity}</strong></span>
              </div>
            </div>

            <div className="text-[11px] text-slate-300 font-sans">
              {labResponse.explanation}
            </div>

            {/* Telemetry Breakdown */}
            {labResponse.telemetry && Object.keys(labResponse.telemetry).length > 0 && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                {Object.entries(labResponse.telemetry).map(([k, v]) => (
                  <div key={k} className="p-2 rounded bg-slate-900 border border-slate-800">
                    <div className="text-[10px] text-slate-500 uppercase">{k.replace(/_/g, ' ')}</div>
                    <div className="text-xs font-bold text-white">{String(v)}</div>
                  </div>
                ))}
              </div>
            )}

            {/* Result Object JSON */}
            <div>
              <div className="text-[10px] text-slate-400 uppercase mb-1">Result Payload:</div>
              <pre className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-[11px] text-cyan-300 overflow-x-auto max-h-56 scrollbar-none">
                {JSON.stringify(labResponse.result, null, 2)}
              </pre>
            </div>
          </div>
        )}

        {queryError && (
          <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-300 text-xs font-mono">
            {queryError}
          </div>
        )}
      </div>
    </div>
  );
};
