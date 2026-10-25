import React, { useState } from 'react';
import {
  Calendar,
  Users,
  Plane,
  AlertTriangle,
  ShieldAlert,
  X,
} from 'lucide-react';
import { FlightLeg, CrewMember, Aircraft, RuleViolation } from '../types';

interface RosterPlannerViewProps {
  flights: FlightLeg[];
  crewList: CrewMember[];
  aircraftList: Aircraft[];
  onManualAssign: (payload: {
    flight_number: string;
    captain_id: string;
    first_officer_id: string;
    cabin_crew_ids: string[];
    aircraft_tail: string;
  }) => Promise<void>;
}

export const RosterPlannerView: React.FC<RosterPlannerViewProps> = ({
  flights,
  crewList,
  aircraftList,
  onManualAssign,
}) => {
  const [filterMode, setFilterMode] = useState<'ALL' | 'ASSIGNED' | 'UNASSIGNED'>('ALL');
  const [selectedUncoveredFlight, setSelectedUncoveredFlight] = useState<FlightLeg | null>(null);

  // Manual Assignment Modal State
  const [manualModalFlight, setManualModalFlight] = useState<FlightLeg | null>(null);
  const [selectedCaptain, setSelectedCaptain] = useState('');
  const [selectedFO, setSelectedFO] = useState('');
  const [selectedCabin, setSelectedCabin] = useState<string[]>([]);
  const [selectedTail, setSelectedTail] = useState('');
  const [isSubmittingManual, setIsSubmittingManual] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);
  const [manualViolations, setManualViolations] = useState<RuleViolation[]>([]);

  const captains = crewList.filter((c) => c.role === 'CAPTAIN' && c.is_active);
  const firstOfficers = crewList.filter((c) => c.role === 'FIRST_OFFICER' && c.is_active);
  const cabinCrew = crewList.filter((c) => c.role === 'CABIN_CREW' && c.is_active);
  const activeAircraft = aircraftList.filter((a) => a.is_active);

  const filteredFlights = flights.filter((f) => {
    const isCovered = f.is_covered ?? (!!f.captain_id && !!f.first_officer_id);
    if (filterMode === 'ASSIGNED') return isCovered;
    if (filterMode === 'UNASSIGNED') return !isCovered;
    return true;
  });

  const formatUtcTime = (epochSeconds: number) => {
    if (!epochSeconds) return '--:--';
    const d = new Date(epochSeconds * 1000);
    return d.toISOString().replace('T', ' ').substring(5, 16) + 'Z';
  };

  const handleOpenManualModal = (flight: FlightLeg) => {
    setManualModalFlight(flight);
    setSelectedCaptain(flight.captain_id || (captains[0]?.id || ''));
    setSelectedFO(flight.first_officer_id || (firstOfficers[0]?.id || ''));
    setSelectedCabin(flight.cabin_crew_ids && flight.cabin_crew_ids.length > 0 ? flight.cabin_crew_ids : (cabinCrew.slice(0, 2).map(c => c.id)));
    setSelectedTail(flight.aircraft_tail || (activeAircraft[0]?.tail_number || ''));
    setManualError(null);
    setManualViolations([]);
  };

  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualModalFlight) return;
    setIsSubmittingManual(true);
    setManualError(null);
    setManualViolations([]);

    try {
      await onManualAssign({
        flight_number: manualModalFlight.flight_number,
        captain_id: selectedCaptain,
        first_officer_id: selectedFO,
        cabin_crew_ids: selectedCabin,
        aircraft_tail: selectedTail,
      });
      setManualModalFlight(null);
    } catch (err: any) {
      setManualError(err.message || 'Manual assignment rejected');
      // If error contains rule violations JSON string
      try {
        const parsed = JSON.parse(err.message);
        if (parsed.violations) {
          setManualViolations(parsed.violations);
        }
      } catch {
        // regular text error
      }
    } finally {
      setIsSubmittingManual(false);
    }
  };

  const handleToggleCabin = (crewId: string) => {
    if (selectedCabin.includes(crewId)) {
      setSelectedCabin(selectedCabin.filter((id) => id !== crewId));
    } else {
      setSelectedCabin([...selectedCabin, crewId]);
    }
  };

  return (
    <div className="space-y-5">
      {/* Top Banner and Filter Pills */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Calendar className="w-5 h-5 text-cyan-400" />
            <span>Roster & Aircraft Rotation Planner</span>
          </h2>
          <p className="text-xs text-slate-400">
            Fail-closed DGCA CAR Sec 7 Series J pairing verification with intra-duty multi-leg continuity
          </p>
        </div>

        <div className="flex items-center gap-2">
          {(['ALL', 'ASSIGNED', 'UNASSIGNED'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setFilterMode(mode)}
              className={`px-3 py-1 rounded-lg text-xs font-mono font-medium transition ${
                filterMode === mode
                  ? 'bg-cyan-600 text-white font-bold'
                  : 'bg-slate-900 border border-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              {mode} ({flights.filter((f) => {
                const c = f.is_covered ?? (!!f.captain_id && !!f.first_officer_id);
                return mode === 'ALL' ? true : mode === 'ASSIGNED' ? c : !c;
              }).length})
            </button>
          ))}
        </div>
      </div>

      {/* Pairing Cards / Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
        {filteredFlights.map((flight) => {
          const isCovered = flight.is_covered ?? (!!flight.captain_id && !!flight.first_officer_id);

          return (
            <div
              key={flight.flight_number}
              className={`p-4 rounded-xl border transition shadow-sm space-y-3 ${
                isCovered
                  ? 'bg-slate-900/90 border-slate-800 hover:border-slate-700'
                  : 'bg-amber-950/20 border-amber-800/40 hover:border-amber-700/60'
              }`}
            >
              {/* Card Header: Flight Number & Status */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 font-mono">
                  <span className="text-sm font-bold text-cyan-300">
                    {flight.flight_number}
                  </span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400">
                    {flight.aircraft_type}
                  </span>
                </div>
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
                    isCovered
                      ? 'bg-emerald-950/70 text-emerald-400 border-emerald-800/60'
                      : 'bg-amber-950/70 text-amber-400 border-amber-800/60'
                  }`}
                >
                  {isCovered ? 'ASSIGNED' : 'UNASSIGNED'}
                </span>
              </div>

              {/* Route & Times */}
              <div className="p-2.5 rounded-lg bg-slate-950/90 border border-slate-800/80 font-mono text-xs space-y-1">
                <div className="flex items-center justify-between text-slate-300">
                  <span className="font-bold text-white text-sm">{flight.origin}</span>
                  <span className="text-slate-600">────────✈────────</span>
                  <span className="font-bold text-white text-sm">{flight.destination}</span>
                </div>
                <div className="flex items-center justify-between text-[11px] text-slate-400">
                  <span>DEP: {formatUtcTime(flight.effective_departure_utc || flight.departure_utc)}</span>
                  <span>ARR: {formatUtcTime(flight.effective_arrival_utc || flight.arrival_utc)}</span>
                </div>
              </div>

              {/* Aircraft Tail */}
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-slate-400 flex items-center gap-1.5">
                  <Plane className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Tail:</span>
                </span>
                <span className="font-bold text-slate-200">
                  {flight.aircraft_tail ? (
                    <span className="text-cyan-400">{flight.aircraft_tail}</span>
                  ) : (
                    <span className="text-amber-400 italic">No Tail Allocated</span>
                  )}
                </span>
              </div>

              {/* Crew Complement */}
              <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800/80 space-y-1 text-xs">
                <div className="flex items-center justify-between text-[11px] font-mono">
                  <span className="text-slate-400">Captain (CPT):</span>
                  <span className={flight.captain_id ? 'text-white font-bold' : 'text-amber-400 italic'}>
                    {flight.captain_id || 'Unassigned'}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[11px] font-mono">
                  <span className="text-slate-400">First Officer (FO):</span>
                  <span className={flight.first_officer_id ? 'text-white font-bold' : 'text-amber-400 italic'}>
                    {flight.first_officer_id || 'Unassigned'}
                  </span>
                </div>
                {flight.cabin_crew_ids && flight.cabin_crew_ids.length > 0 && (
                  <div className="pt-1 border-t border-slate-900 text-[10px] text-slate-400 font-mono">
                    Cabin: {flight.cabin_crew_ids.join(', ')}
                  </div>
                )}
              </div>

              {/* Uncovered Reason Pill if unassigned */}
              {!isCovered && (
                <div className="space-y-1">
                  <div className="p-2 rounded bg-amber-950/40 border border-amber-900/60 text-amber-300 text-[11px] flex items-center justify-between">
                    <span className="truncate">
                      Cause: {flight.uncovered_reason?.primary_cause || 'Candidate rule rejection'}
                    </span>
                    <button
                      onClick={() => setSelectedUncoveredFlight(flight)}
                      className="text-[10px] underline hover:text-white shrink-0 ml-1 font-mono"
                    >
                      Audit
                    </button>
                  </div>
                </div>
              )}

              {/* Card Footer: Manual Assign Trigger */}
              <div className="pt-1 flex items-center justify-end">
                <button
                  onClick={() => handleOpenManualModal(flight)}
                  className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition flex items-center gap-1"
                >
                  <Users className="w-3 h-3 text-cyan-400" />
                  <span>Manual Assign</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Uncovered Reason Audit Modal */}
      {selectedUncoveredFlight && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                <h3 className="text-sm font-semibold text-white">
                  Constraint Failure Audit: {selectedUncoveredFlight.flight_number}
                </h3>
              </div>
              <button
                onClick={() => setSelectedUncoveredFlight(null)}
                className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div className="p-3 rounded bg-slate-950 border border-slate-800 space-y-1">
                <div>Primary Cause: <strong className="text-amber-400">{selectedUncoveredFlight.uncovered_reason?.primary_cause || 'All candidates violated hard constraints'}</strong></div>
                <div className="text-slate-400">{selectedUncoveredFlight.uncovered_reason?.summary || 'No legal aircraft or crew pairing found satisfying fail-closed safety parameters.'}</div>
              </div>

              {/* Aircraft Violations */}
              {selectedUncoveredFlight.uncovered_reason?.aircraft_violations &&
                selectedUncoveredFlight.uncovered_reason.aircraft_violations.length > 0 && (
                  <div className="space-y-1">
                    <div className="text-[11px] text-slate-400 font-bold uppercase">Aircraft Hard Rejections:</div>
                    <div className="max-h-28 overflow-y-auto space-y-1">
                      {selectedUncoveredFlight.uncovered_reason.aircraft_violations.map((v, i) => (
                        <div key={i} className="p-1.5 rounded bg-rose-950/40 border border-rose-900/60 text-rose-300 text-[11px]">
                          <strong>[{v.rule_id}]</strong> {v.message}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

              {/* Crew Violations */}
              {selectedUncoveredFlight.uncovered_reason?.crew_violations &&
                selectedUncoveredFlight.uncovered_reason.crew_violations.length > 0 && (
                  <div className="space-y-1">
                    <div className="text-[11px] text-slate-400 font-bold uppercase">Crew Hard Rejections:</div>
                    <div className="max-h-28 overflow-y-auto space-y-1">
                      {selectedUncoveredFlight.uncovered_reason.crew_violations.map((v, i) => (
                        <div key={i} className="p-1.5 rounded bg-rose-950/40 border border-rose-900/60 text-rose-300 text-[11px]">
                          <strong>[{v.rule_id}]</strong> {v.message} ({v.entity_id})
                        </div>
                      ))}
                    </div>
                  </div>
                )}

              <div className="pt-2 text-[11px] text-slate-500 font-sans">
                Academic Invariant: Hard constraints cannot be overridden. Flight remains UNASSIGNED until an eligible aircraft and crew schedule window opens.
              </div>
            </div>

            <div className="flex justify-end pt-2 border-t border-slate-800">
              <button
                onClick={() => setSelectedUncoveredFlight(null)}
                className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 hover:text-white text-xs font-semibold"
              >
                Close Audit
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Manual Assignment Modal */}
      {manualModalFlight && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Users className="w-4 h-4 text-cyan-400" />
                <h3 className="text-sm font-semibold text-white">
                  Manual Flight Assignment: {manualModalFlight.flight_number}
                </h3>
              </div>
              <button
                onClick={() => setManualModalFlight(null)}
                className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleManualSubmit} className="space-y-3.5 text-xs font-mono">
              <div className="p-2.5 rounded bg-slate-950 border border-slate-800/80 flex items-center justify-between">
                <div>Route: <strong className="text-white">{manualModalFlight.origin} → {manualModalFlight.destination}</strong></div>
                <div>Scheduled: <span className="text-slate-300">{formatUtcTime(manualModalFlight.departure_utc)}</span></div>
                <div>Type: <span className="text-cyan-400">{manualModalFlight.aircraft_type}</span></div>
              </div>

              {/* Aircraft Tail Selection */}
              <div>
                <label className="block text-slate-400 mb-1">Aircraft Tail ({manualModalFlight.aircraft_type}):</label>
                <select
                  value={selectedTail}
                  onChange={(e) => setSelectedTail(e.target.value)}
                  className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white font-semibold"
                  required
                >
                  <option value="">Select Aircraft</option>
                  {activeAircraft.map((a) => (
                    <option key={a.tail_number} value={a.tail_number}>
                      {a.tail_number} ({a.aircraft_type} — Base: {a.home_base})
                    </option>
                  ))}
                </select>
              </div>

              {/* Captain Selection */}
              <div>
                <label className="block text-slate-400 mb-1">Captain (CPT):</label>
                <select
                  value={selectedCaptain}
                  onChange={(e) => setSelectedCaptain(e.target.value)}
                  className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white font-semibold"
                  required
                >
                  <option value="">Select Captain</option>
                  {captains.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.id} — Base: {c.home_base})
                    </option>
                  ))}
                </select>
              </div>

              {/* First Officer Selection */}
              <div>
                <label className="block text-slate-400 mb-1">First Officer (FO):</label>
                <select
                  value={selectedFO}
                  onChange={(e) => setSelectedFO(e.target.value)}
                  className="w-full p-2 rounded bg-slate-950 border border-slate-800 text-white font-semibold"
                  required
                >
                  <option value="">Select First Officer</option>
                  {firstOfficers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.id} — Base: {c.home_base})
                    </option>
                  ))}
                </select>
              </div>

              {/* Cabin Crew Checkboxes */}
              <div>
                <label className="block text-slate-400 mb-1">
                  Cabin Crew ({selectedCabin.length} selected):
                </label>
                <div className="max-h-24 overflow-y-auto p-2 rounded bg-slate-950 border border-slate-800 grid grid-cols-2 gap-1.5">
                  {cabinCrew.map((c) => (
                    <label key={c.id} className="flex items-center gap-1.5 text-[11px] text-slate-300 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedCabin.includes(c.id)}
                        onChange={() => handleToggleCabin(c.id)}
                        className="rounded border-slate-700 text-cyan-500 focus:ring-0"
                      />
                      <span>{c.name} ({c.id})</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Errors / Violations */}
              {manualError && (
                <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-300 space-y-1">
                  <div className="font-bold flex items-center gap-1.5">
                    <ShieldAlert className="w-3.5 h-3.5" />
                    <span>Transaction Rolled Back (HTTP 422 Fail-Closed):</span>
                  </div>
                  <div className="text-[11px]">{manualError}</div>
                  {manualViolations.length > 0 && (
                    <div className="space-y-1 pt-1 border-t border-rose-900/60 text-[10px]">
                      {manualViolations.map((v, i) => (
                        <div key={i}>
                          <strong>[{v.rule_id}]</strong> {v.message} ({v.entity_id})
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setManualModalFlight(null)}
                  className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingManual}
                  className="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-semibold transition"
                >
                  {isSubmittingManual ? 'Validating Rules...' : 'Submit Assignment'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
