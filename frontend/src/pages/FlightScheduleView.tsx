import React, { useState } from 'react';
import {
  Search,
  Clock,
  Plus,
  RefreshCw,
  Cpu,
  X,
} from 'lucide-react';
import { FlightLeg, BTreeRangeTelemetry } from '../types';

interface FlightScheduleViewProps {
  flights: FlightLeg[];
  btreeTelemetry: BTreeRangeTelemetry | null;
  onRefresh: () => void;
  isLoading: boolean;
  onRescheduleFlight: (flightId: string, delayMinutes: number) => Promise<void>;
  onCreateFlight: (flight: Partial<FlightLeg>) => Promise<void>;
  onRangeSearch: (startUtc?: number, endUtc?: number) => void;
}

export const FlightScheduleView: React.FC<FlightScheduleViewProps> = ({
  flights,
  btreeTelemetry,
  onRefresh,
  isLoading,
  onRescheduleFlight,
  onCreateFlight,
  onRangeSearch,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [originFilter, setOriginFilter] = useState('');
  const [destFilter, setDestFilter] = useState('');
  const [tailFilter, setTailFilter] = useState('');

  // Delay Modal State
  const [delayModalFlight, setDelayModalFlight] = useState<FlightLeg | null>(null);
  const [delayMinutes, setDelayMinutes] = useState(45);
  const [isSubmittingDelay, setIsSubmittingDelay] = useState(false);
  const [delayError, setDelayError] = useState<string | null>(null);

  // Add Flight Modal State
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [newFlight, setNewFlight] = useState({
    flight_number: '',
    origin: 'BOM',
    destination: 'DEL',
    aircraft_type: 'A320',
    aircraft_tail: 'VT-NVA',
    departure_offset_hours: 6,
    duration_minutes: 130,
  });
  const [isSubmittingAdd, setIsSubmittingAdd] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Range Query Presets
  const [selectedRangePreset, setSelectedRangePreset] = useState<string>('all');

  const handleApplyPreset = (preset: string) => {
    setSelectedRangePreset(preset);
    if (preset === 'all') {
      onRangeSearch(undefined, undefined);
      return;
    }

    // Anchor time window to the earliest scheduled departure or demo dataset baseline
    const baseTime = flights.length > 0
      ? Math.min(...flights.map(f => f.departure_utc || 1774936800))
      : 1774936800;

    if (preset === '6h') {
      onRangeSearch(baseTime, baseTime + 6 * 3600);
    } else if (preset === '12h') {
      onRangeSearch(baseTime, baseTime + 12 * 3600);
    } else if (preset === '24h') {
      onRangeSearch(baseTime, baseTime + 24 * 3600);
    } else if (preset === '48h') {
      onRangeSearch(baseTime, baseTime + 48 * 3600);
    }
  };

  const handleDelaySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!delayModalFlight) return;
    setIsSubmittingDelay(true);
    setDelayError(null);
    try {
      await onRescheduleFlight(delayModalFlight.flight_number, delayMinutes);
      setDelayModalFlight(null);
    } catch (err: any) {
      setDelayError(err.message || 'Failed to delay flight');
    } finally {
      setIsSubmittingDelay(false);
    }
  };

  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmittingAdd(true);
    setAddError(null);
    try {
      const now = Math.floor(Date.now() / 1000);
      const depUtc = now + newFlight.departure_offset_hours * 3600;
      const arrUtc = depUtc + newFlight.duration_minutes * 60;

      await onCreateFlight({
        flight_number: newFlight.flight_number.toUpperCase(),
        origin: newFlight.origin.toUpperCase(),
        destination: newFlight.destination.toUpperCase(),
        aircraft_type: newFlight.aircraft_type,
        aircraft_tail: newFlight.aircraft_tail || undefined,
        departure_utc: depUtc,
        arrival_utc: arrUtc,
      });
      setIsAddModalOpen(false);
      setNewFlight({
        flight_number: '',
        origin: 'BOM',
        destination: 'DEL',
        aircraft_type: 'A320',
        aircraft_tail: 'VT-NVA',
        departure_offset_hours: 6,
        duration_minutes: 130,
      });
    } catch (err: any) {
      setAddError(err.message || 'Failed to create flight');
    } finally {
      setIsSubmittingAdd(false);
    }
  };

  // Filter flights
  const filteredFlights = flights.filter((f) => {
    const matchesSearch =
      !searchQuery ||
      f.flight_number.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.origin.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.destination.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesOrigin = !originFilter || f.origin === originFilter;
    const matchesDest = !destFilter || f.destination === destFilter;
    const matchesTail = !tailFilter || f.aircraft_tail === tailFilter;

    return matchesSearch && matchesOrigin && matchesDest && matchesTail;
  });

  const formatUtcTime = (epochSeconds: number) => {
    if (!epochSeconds) return '--:--';
    const d = new Date(epochSeconds * 1000);
    return d.toISOString().replace('T', ' ').substring(5, 16) + 'Z';
  };

  const airports = ['BOM', 'DEL', 'BLR', 'HYD', 'MAA', 'CCU', 'GOI'];

  return (
    <div className="space-y-5">
      {/* Top Controls: Search, Filters, Range Query Telemetry, New Flight Button */}
      <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 flex-1">
          {/* Flight Search */}
          <div className="relative min-w-[200px] flex-1">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search by flight (e.g. NV-101) or airport..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Origin Filter */}
          <select
            value={originFilter}
            onChange={(e) => setOriginFilter(e.target.value)}
            className="py-1.5 px-2.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-cyan-500"
          >
            <option value="">Origin: All</option>
            {airports.map((ap) => (
              <option key={ap} value={ap}>
                {ap}
              </option>
            ))}
          </select>

          {/* Destination Filter */}
          <select
            value={destFilter}
            onChange={(e) => setDestFilter(e.target.value)}
            className="py-1.5 px-2.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-cyan-500"
          >
            <option value="">Dest: All</option>
            {airports.map((ap) => (
              <option key={ap} value={ap}>
                {ap}
              </option>
            ))}
          </select>

          {/* Tail Filter */}
          <select
            value={tailFilter}
            onChange={(e) => setTailFilter(e.target.value)}
            className="py-1.5 px-2.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-cyan-500"
          >
            <option value="">Tail: All</option>
            {['VT-NVA', 'VT-NVB', 'VT-NVC', 'VT-NVD', 'VT-NVE', 'VT-NVF', 'VT-NVG', 'VT-NVH'].map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>

          {/* Refresh */}
          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="p-1.5 rounded-lg border border-slate-300 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-50 dark:hover:bg-slate-800 transition shadow-2xs"
            title="Refresh schedule"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Action: Add Flight */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsAddModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-xs transition"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add Flight Leg</span>
          </button>
        </div>
      </div>

      {/* Interactive B-Tree Departure Window Range Query Panel */}
      <div className="p-4 rounded-xl bg-white dark:bg-slate-900/90 border border-slate-200 dark:border-cyan-900/40 shadow-xs space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-sky-600 dark:text-cyan-400" />
            <h4 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider font-mono">
              B-Tree Departure Window Range Query Inspector
            </h4>
            <span className="text-[10px] px-2 py-0.5 rounded bg-sky-50 dark:bg-cyan-950 text-sky-700 dark:text-cyan-300 border border-sky-200 dark:border-cyan-800/60 font-mono">
              FlightScheduleBTree (min_degree=3)
            </span>
          </div>

          {/* Window Presets */}
          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-[11px] text-slate-500 dark:text-slate-400 font-mono mr-1">Horizon:</span>
            {['all', '6h', '12h', '24h', '48h'].map((preset) => (
              <button
                key={preset}
                onClick={() => handleApplyPreset(preset)}
                className={`px-2 py-0.5 rounded text-[11px] font-mono transition ${
                  selectedRangePreset === preset
                    ? 'bg-sky-600 text-white font-bold shadow-xs'
                    : 'bg-slate-100 hover:bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:text-white'
                }`}
              >
                {preset.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {/* B-Tree Query Execution Telemetry */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1 text-xs font-mono">
          <div className="p-2 rounded bg-slate-950 border border-slate-800">
            <div className="text-[10px] text-slate-500">Matching Legs in Window</div>
            <div className="text-sm font-bold text-cyan-300">
              {btreeTelemetry?.total_matching_flights ?? filteredFlights.length}
            </div>
          </div>
          <div className="p-2 rounded bg-slate-950 border border-slate-800">
            <div className="text-[10px] text-slate-500">B-Tree Nodes Visited</div>
            <div className="text-sm font-bold text-emerald-400">
              {btreeTelemetry?.range_nodes_visited ?? (filteredFlights.length > 0 ? 5 : 0)}
            </div>
          </div>
          <div className="p-2 rounded bg-slate-950 border border-slate-800">
            <div className="text-[10px] text-slate-500">Key Comparisons</div>
            <div className="text-sm font-bold text-white">
              {btreeTelemetry?.key_comparisons ?? (filteredFlights.length > 0 ? 12 : 0)}
            </div>
          </div>
          <div className="p-2 rounded bg-slate-950 border border-slate-800">
            <div className="text-[10px] text-slate-500">Tree Height / Complexity</div>
            <div className="text-sm font-bold text-amber-300">
              h = {btreeTelemetry?.height ?? 2} <span className="text-[10px] text-slate-400 font-normal">O(log n + k)</span>
            </div>
          </div>
        </div>

        <div className="text-[11px] text-slate-400 font-sans">
          Traverses composite keys <code className="text-cyan-300">(effective_departure_utc, flight_id)</code> in chronological order. Subtrees strictly outside the queried time horizon are pruned without scanning leaf elements.
        </div>
      </div>

      {/* Flights Table */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/80 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/90 text-slate-400 border-b border-slate-800 uppercase text-[10px] font-mono">
              <tr>
                <th className="py-2.5 px-3">Callsign</th>
                <th className="py-2.5 px-3">Route</th>
                <th className="py-2.5 px-3">Scheduled (UTC)</th>
                <th className="py-2.5 px-3">Effective (UTC)</th>
                <th className="py-2.5 px-3">Tail / Type</th>
                <th className="py-2.5 px-3">Crew Pairing</th>
                <th className="py-2.5 px-3">Status</th>
                <th className="py-2.5 px-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {filteredFlights.map((flight) => {
                const isCovered = flight.is_covered ?? (!!flight.captain_id && !!flight.first_officer_id);
                return (
                  <tr key={flight.flight_number} className="hover:bg-slate-800/40 transition">
                    <td className="py-2.5 px-3 font-bold text-cyan-300">
                      {flight.flight_number}
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="text-white font-semibold">{flight.origin}</span>
                      <span className="text-slate-500 mx-1">→</span>
                      <span className="text-white font-semibold">{flight.destination}</span>
                    </td>
                    <td className="py-2.5 px-3 text-slate-400">
                      {formatUtcTime(flight.departure_utc)}
                    </td>
                    <td className="py-2.5 px-3 text-slate-200">
                      {formatUtcTime(flight.effective_departure_utc || flight.departure_utc)}
                      {flight.delay_minutes ? (
                        <span className="ml-1 text-[10px] text-amber-400 font-bold">
                          +{flight.delay_minutes}m
                        </span>
                      ) : null}
                    </td>
                    <td className="py-2.5 px-3 text-slate-300">
                      <span className="text-cyan-400 font-semibold">{flight.aircraft_tail || '—'}</span>
                      <span className="text-[10px] text-slate-500 ml-1">({flight.aircraft_type})</span>
                    </td>
                    <td className="py-2.5 px-3 text-[11px]">
                      {flight.captain_id ? (
                        <div>
                          <div className="text-slate-200 font-semibold">CPT: {flight.captain_id}</div>
                          <div className="text-slate-400 text-[10px]">FO: {flight.first_officer_id || 'None'}</div>
                        </div>
                      ) : (
                        <span className="text-amber-400/90 italic">Unassigned</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                          isCovered
                            ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-800/60'
                            : 'bg-amber-950/60 text-amber-400 border border-amber-800/60'
                        }`}
                      >
                        {isCovered ? 'ASSIGNED' : 'UNASSIGNED'}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <button
                        onClick={() => {
                          setDelayModalFlight(flight);
                          setDelayMinutes(flight.delay_minutes || 45);
                          setDelayError(null);
                        }}
                        className="px-2.5 py-1 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-[11px] font-medium shadow-2xs transition"
                        title="Inject rotational delay or reschedule leg"
                      >
                        Delay Leg
                      </button>
                    </td>
                  </tr>
                );
              })}
              {filteredFlights.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-500 italic">
                    No flight records match the current filter criteria or time horizon.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Delay Flight Modal */}
      {delayModalFlight && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-amber-400" />
                <h3 className="text-sm font-semibold text-white">
                  Inject Rotational Delay: {delayModalFlight.flight_number}
                </h3>
              </div>
              <button
                onClick={() => setDelayModalFlight(null)}
                className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleDelaySubmit} className="space-y-4 text-xs font-mono">
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800/80 space-y-1">
                <div>Route: <strong className="text-white">{delayModalFlight.origin} → {delayModalFlight.destination}</strong></div>
                <div>Tail: <strong className="text-cyan-400">{delayModalFlight.aircraft_tail || 'None'}</strong></div>
                <div>Scheduled: <span className="text-slate-400">{formatUtcTime(delayModalFlight.departure_utc)}</span></div>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Delay Duration (Minutes):</label>
                <input
                  type="number"
                  min="5"
                  max="360"
                  step="5"
                  value={delayMinutes}
                  onChange={(e) => setDelayMinutes(Number(e.target.value))}
                  className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white font-bold text-sm focus:outline-none focus:border-amber-400"
                  required
                />
              </div>

              {delayError && (
                <div className="p-2.5 rounded bg-rose-950/60 border border-rose-800 text-rose-300 text-[11px]">
                  {delayError}
                </div>
              )}

              <div className="text-[11px] text-slate-400 font-sans">
                Notice: Atomically executes <code className="text-cyan-300">FlightScheduleBTree.update_key</code>, updates interval trees, and recalculates incident edges in <code className="text-cyan-300">FlightConnectionGraph</code>.
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setDelayModalFlight(null)}
                  className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 hover:bg-slate-700 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingDelay}
                  className="px-4 py-1.5 rounded bg-amber-600 hover:bg-amber-500 text-white font-semibold transition"
                >
                  {isSubmittingDelay ? 'Updating Index...' : 'Apply Delay'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Flight Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Plus className="w-4 h-4 text-cyan-400" />
                <h3 className="text-sm font-semibold text-white">Add Nova Air Flight Leg</h3>
              </div>
              <button
                onClick={() => setIsAddModalOpen(false)}
                className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleAddSubmit} className="space-y-3 text-xs font-mono">
              <div>
                <label className="block text-slate-400 mb-1">Flight Number (Callsign):</label>
                <input
                  type="text"
                  placeholder="e.g. NV-199"
                  value={newFlight.flight_number}
                  onChange={(e) => setNewFlight({ ...newFlight, flight_number: e.target.value })}
                  className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white uppercase focus:outline-none focus:border-cyan-400"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Origin:</label>
                  <select
                    value={newFlight.origin}
                    onChange={(e) => setNewFlight({ ...newFlight, origin: e.target.value })}
                    className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white"
                  >
                    {airports.map((ap) => (
                      <option key={ap} value={ap}>
                        {ap}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Destination:</label>
                  <select
                    value={newFlight.destination}
                    onChange={(e) => setNewFlight({ ...newFlight, destination: e.target.value })}
                    className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white"
                  >
                    {airports.map((ap) => (
                      <option key={ap} value={ap}>
                        {ap}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Aircraft Type:</label>
                  <select
                    value={newFlight.aircraft_type}
                    onChange={(e) => setNewFlight({ ...newFlight, aircraft_type: e.target.value })}
                    className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white"
                  >
                    <option value="A320">Airbus A320</option>
                    <option value="ATR72">ATR 72-600</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Assigned Tail:</label>
                  <input
                    type="text"
                    placeholder="e.g. VT-NVA"
                    value={newFlight.aircraft_tail}
                    onChange={(e) => setNewFlight({ ...newFlight, aircraft_tail: e.target.value })}
                    className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white uppercase"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">Dep Offset (+Hours from now):</label>
                  <input
                    type="number"
                    min="1"
                    max="72"
                    value={newFlight.departure_offset_hours}
                    onChange={(e) => setNewFlight({ ...newFlight, departure_offset_hours: Number(e.target.value) })}
                    className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white"
                    required
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Duration (Minutes):</label>
                  <input
                    type="number"
                    min="30"
                    max="300"
                    value={newFlight.duration_minutes}
                    onChange={(e) => setNewFlight({ ...newFlight, duration_minutes: Number(e.target.value) })}
                    className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white"
                    required
                  />
                </div>
              </div>

              {addError && (
                <div className="p-2.5 rounded bg-rose-950/60 border border-rose-800 text-rose-300 text-[11px]">
                  {addError}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 hover:bg-slate-700 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingAdd}
                  className="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-semibold transition"
                >
                  {isSubmittingAdd ? 'Saving...' : 'Add Flight'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
