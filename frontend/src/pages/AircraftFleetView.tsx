import React, { useState } from 'react';
import {
  Layers,
  Plane,
  X,
} from 'lucide-react';
import { Aircraft, FlightLeg } from '../types';
import { api } from '../services/api';

interface AircraftFleetViewProps {
  aircraftList: Aircraft[];
  flights: FlightLeg[];
}

export const AircraftFleetView: React.FC<AircraftFleetViewProps> = ({
  aircraftList,
  flights,
}) => {
  const [selectedTail, setSelectedTail] = useState<Aircraft | null>(null);
  const [tailRotation, setTailRotation] = useState<FlightLeg[]>([]);
  const [isLoadingRotation, setIsLoadingRotation] = useState(false);

  const handleOpenRotation = async (aircraft: Aircraft) => {
    setSelectedTail(aircraft);
    setIsLoadingRotation(true);
    try {
      const rotation = await api.getAircraftRotation(aircraft.tail_number);
      setTailRotation(rotation);
    } catch {
      setTailRotation([]);
    } finally {
      setIsLoadingRotation(false);
    }
  };

  const formatUtcTime = (epochSeconds: number) => {
    if (!epochSeconds) return '--:--';
    const d = new Date(epochSeconds * 1000);
    return d.toISOString().replace('T', ' ').substring(5, 16) + 'Z';
  };

  // Group flights by assigned tail
  const flightsByTail: Record<string, FlightLeg[]> = {};
  flights.forEach((f) => {
    if (f.aircraft_tail) {
      if (!flightsByTail[f.aircraft_tail]) flightsByTail[f.aircraft_tail] = [];
      flightsByTail[f.aircraft_tail].push(f);
    }
  });

  // Sort each tail's flights chronologically
  Object.keys(flightsByTail).forEach((tail) => {
    flightsByTail[tail].sort((a, b) => (a.departure_utc || 0) - (b.departure_utc || 0));
  });

  return (
    <div className="space-y-5">
      {/* Top Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Layers className="w-5 h-5 text-cyan-400" />
            <span>Aircraft Fleet & Rotation Continuity</span>
          </h2>
          <p className="text-xs text-slate-400">
            Tail allocations, minimum TAT turnaround buffers (A320: 45m, ATR72: 30m), and maintenance intervals
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono">
          <span className="text-slate-400">Fleet Strength:</span>
          <span className="px-2.5 py-1 rounded bg-slate-900 border border-slate-800 text-white font-bold">
            {aircraftList.length} Aircraft ({aircraftList.filter((a) => a.is_active).length} Serviceable)
          </span>
        </div>
      </div>

      {/* Fleet Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3.5">
        {aircraftList.map((ac) => {
          const tailFlights = flightsByTail[ac.tail_number] || [];

          return (
            <div
              key={ac.tail_number}
              className={`p-4 rounded-xl border transition shadow-sm space-y-3 ${
                ac.is_active
                  ? 'bg-slate-900/90 border-slate-800 hover:border-slate-700'
                  : 'bg-rose-950/20 border-rose-900/40 hover:border-rose-800/60'
              }`}
            >
              {/* Header */}
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-bold text-cyan-300 font-mono">
                    {ac.tail_number}
                  </div>
                  <div className="text-[11px] text-slate-400 font-mono">
                    {ac.aircraft_type === 'A320' ? 'Airbus A320' : 'ATR 72-600'} · Base: <strong className="text-white">{ac.home_base}</strong>
                  </div>
                </div>

                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                    ac.is_active
                      ? 'bg-emerald-950/70 text-emerald-400 border border-emerald-800/60'
                      : 'bg-rose-950/70 text-rose-400 border border-rose-800/60'
                  }`}
                >
                  {ac.is_active ? 'SERVICEABLE' : 'AOG / MAINT'}
                </span>
              </div>

              {/* Specs */}
              <div className="p-2.5 rounded-lg bg-slate-950/90 border border-slate-800/80 font-mono text-xs space-y-1">
                <div className="flex items-center justify-between text-slate-400 text-[11px]">
                  <span>Seating Capacity:</span>
                  <span className="text-white font-bold">{ac.seating_capacity} seats</span>
                </div>
                <div className="flex items-center justify-between text-slate-400 text-[11px]">
                  <span>Flight Hours:</span>
                  <span className="text-white font-bold">{ac.total_flight_hours} hrs</span>
                </div>
                <div className="flex items-center justify-between text-slate-400 text-[11px]">
                  <span>Scheduled Legs:</span>
                  <span className="text-cyan-400 font-bold">{tailFlights.length} sectors</span>
                </div>
              </div>

              {/* Rotation Chain Preview */}
              <div className="space-y-1">
                <div className="text-[10px] text-slate-400 uppercase font-mono">Rotation Sequence:</div>
                <div className="flex flex-wrap items-center gap-1 font-mono text-[10px]">
                  {tailFlights.slice(0, 4).map((f, idx) => (
                    <React.Fragment key={f.flight_number}>
                      <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-200">
                        {f.origin}→{f.destination}
                      </span>
                      {idx < Math.min(tailFlights.length, 4) - 1 && (
                        <span className="text-slate-600">›</span>
                      )}
                    </React.Fragment>
                  ))}
                  {tailFlights.length > 4 && (
                    <span className="text-slate-500 text-[10px]">+{tailFlights.length - 4} more</span>
                  )}
                  {tailFlights.length === 0 && (
                    <span className="text-slate-500 italic text-[11px]">No sectors assigned</span>
                  )}
                </div>
              </div>

              {/* Card Footer */}
              <div className="pt-2 border-t border-slate-800 flex justify-end">
                <button
                  onClick={() => handleOpenRotation(ac)}
                  className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-medium transition flex items-center gap-1.5"
                >
                  <Plane className="w-3 h-3 text-cyan-400" />
                  <span>Inspect Rotation Chain</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Rotation Chain Timeline Modal */}
      {selectedTail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-xl bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Plane className="w-4 h-4 text-cyan-400" />
                <h3 className="text-sm font-semibold text-white">
                  Rotation Continuity: {selectedTail.tail_number} ({selectedTail.aircraft_type})
                </h3>
              </div>
              <button
                onClick={() => setSelectedTail(null)}
                className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 font-mono text-xs">
              <div className="p-2.5 rounded bg-slate-950 border border-slate-800 text-[11px] flex items-center justify-between">
                <div>Type: <strong className="text-white">{selectedTail.aircraft_type}</strong> | Base: <strong className="text-cyan-400">{selectedTail.home_base}</strong></div>
                <div className="text-slate-400">
                  TAT Buffer Requirement: <strong className="text-amber-400">{selectedTail.aircraft_type === 'A320' ? '45 min' : '30 min'}</strong>
                </div>
              </div>

              {isLoadingRotation ? (
                <div className="py-8 text-center text-slate-400">Loading rotation intervals...</div>
              ) : tailRotation.length === 0 ? (
                <div className="py-8 text-center text-slate-500 italic">
                  No flight or maintenance intervals assigned to this tail.
                </div>
              ) : (
                <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                  {tailRotation.map((flight, idx) => {
                    const nextFlight = tailRotation[idx + 1];
                    const turnaroundSlackMin = nextFlight
                      ? Math.round((nextFlight.departure_utc - flight.arrival_utc) / 60)
                      : null;
                    const requiredTatMin = selectedTail.aircraft_type === 'A320' ? 45 : 30;
                    const isTatViolated = turnaroundSlackMin !== null && turnaroundSlackMin < requiredTatMin;

                    return (
                      <div key={flight.flight_number} className="space-y-1.5">
                        <div className="p-2.5 rounded bg-slate-950 border border-slate-800/80 flex items-center justify-between">
                          <div>
                            <div className="text-cyan-300 font-bold">{flight.flight_number}</div>
                            <div className="text-slate-300">
                              {flight.origin} → {flight.destination}
                            </div>
                          </div>
                          <div className="text-right text-[11px] text-slate-400">
                            <div>DEP: {formatUtcTime(flight.effective_departure_utc || flight.departure_utc)}</div>
                            <div>ARR: {formatUtcTime(flight.effective_arrival_utc || flight.arrival_utc)}</div>
                          </div>
                        </div>

                        {/* Turnaround Connection Indicator */}
                        {turnaroundSlackMin !== null && (
                          <div className="flex items-center justify-center gap-2 py-1 text-[10px]">
                            <span className="text-slate-600">│</span>
                            <span
                              className={`px-2 py-0.5 rounded border font-bold ${
                                isTatViolated
                                  ? 'bg-rose-950/60 text-rose-400 border-rose-800'
                                  : 'bg-slate-950 text-slate-400 border-slate-800'
                              }`}
                            >
                              TAT Slack: {turnaroundSlackMin} min (Min: {requiredTatMin} min)
                            </span>
                            <span className="text-slate-600">│</span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="flex justify-end pt-2 border-t border-slate-800">
              <button
                onClick={() => setSelectedTail(null)}
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
