import React, { useState, useEffect, useCallback } from 'react';
import { Navbar } from './components/Navbar';
import { EventDrawer } from './components/EventDrawer';
import { OverviewView } from './pages/OverviewView';
import { FlightScheduleView } from './pages/FlightScheduleView';
import { RosterPlannerView } from './pages/RosterPlannerView';
import { CrewDirectoryView } from './pages/CrewDirectoryView';
import { AircraftFleetView } from './pages/AircraftFleetView';
import { ConstraintInspectorView } from './pages/ConstraintInspectorView';
import { DisruptionSimulatorView } from './pages/DisruptionSimulatorView';
import { ADSLaboratoryView } from './pages/ADSLaboratoryView';
import { useWebSocket } from './hooks/useWebSocket';
import { api } from './services/api';
import {
  NavTab,
  DashboardSummary,
  FlightLeg,
  CrewMember,
  Aircraft,
  BTreeRangeTelemetry,
  WebSocketEvent,
} from './types';

export default function App(): React.ReactElement {
  const [currentTab, setCurrentTab] = useState<NavTab>('overview');
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [flights, setFlights] = useState<FlightLeg[]>([]);
  const [crewList, setCrewList] = useState<CrewMember[]>([]);
  const [aircraftList, setAircraftList] = useState<Aircraft[]>([]);
  const [btreeTelemetry, setBtreeTelemetry] = useState<BTreeRangeTelemetry | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [isEventsDrawerOpen, setIsEventsDrawerOpen] = useState(false);
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);

  const showNotification = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setNotification({ message, type });
    setTimeout(() => {
      setNotification(null);
    }, 4000);
  };

  const loadData = useCallback(async () => {
    try {
      const [sum, fl, cr, ac] = await Promise.all([
        api.getDashboardSummary(),
        api.getFlights(),
        api.getCrew(),
        api.getAircraft(),
      ]);
      setSummary(sum);
      setFlights(fl.flights || []);
      setBtreeTelemetry(fl.btree_range_telemetry || null);
      setCrewList(cr || []);
      setAircraftList(ac || []);
    } catch (err: any) {
      console.error('Failed to load operations data', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // WebSocket Live Hook
  const handleWsEvent = useCallback(
    (_event: WebSocketEvent) => {
      // Whenever an operational event arrives, reload active data
      loadData();
    },
    [loadData]
  );

  const { status: wsStatus, events, lastUpdateUtc, clearEvents } = useWebSocket(handleWsEvent);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Actions
  const handleGenerateRoster = async () => {
    setIsGenerating(true);
    try {
      const res = await api.generateRoster();
      showNotification(`Roster Generated: ${res.roster_count} assigned legs, ${res.unassigned_count} unassigned.`, 'success');
      await loadData();
    } catch (err: any) {
      showNotification(`Roster Generation Failed: ${err.message}`, 'error');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleResetDemo = async (profile: 'demo' | 'test') => {
    setIsResetting(true);
    try {
      const res = await api.resetDemo(profile);
      showNotification(`System Reset: Loaded ${profile.toUpperCase()} profile with ${res.flights_count} flights.`, 'info');
      await loadData();
    } catch (err: any) {
      showNotification(`System Reset Failed: ${err.message}`, 'error');
    } finally {
      setIsResetting(false);
    }
  };

  const handleRescheduleFlight = async (flightId: string, delayMinutes: number) => {
    try {
      await api.rescheduleFlight(flightId, { delay_minutes: delayMinutes });
      showNotification(`Flight ${flightId} rescheduled with +${delayMinutes}m delay.`, 'success');
      await loadData();
    } catch (err: any) {
      showNotification(`Reschedule Failed: ${err.message}`, 'error');
      throw err;
    }
  };

  const handleCreateFlight = async (flight: Partial<FlightLeg>) => {
    try {
      await api.createFlight(flight);
      showNotification(`Flight ${flight.flight_number} scheduled.`, 'success');
      await loadData();
    } catch (err: any) {
      showNotification(`Flight Creation Failed: ${err.message}`, 'error');
      throw err;
    }
  };

  const handleManualAssign = async (payload: {
    flight_number: string;
    captain_id: string;
    first_officer_id: string;
    cabin_crew_ids: string[];
    aircraft_tail: string;
  }) => {
    try {
      await api.manualAssign(payload);
      showNotification(`Flight ${payload.flight_number} manually assigned.`, 'success');
      await loadData();
    } catch (err: any) {
      showNotification(`Assignment Rejected: ${err.message}`, 'error');
      throw err;
    }
  };

  const handleRangeSearch = async (startUtc?: number, endUtc?: number) => {
    try {
      const res = await api.getFlights({ start_time_utc: startUtc, end_time_utc: endUtc });
      setFlights(res.flights || []);
      setBtreeTelemetry(res.btree_range_telemetry || null);
    } catch (err: any) {
      showNotification(`Range Search Failed: ${err.message}`, 'error');
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col selection:bg-cyan-500/30 selection:text-cyan-200">
      {/* Global OCC Navigation Header */}
      <Navbar
        currentTab={currentTab}
        onSelectTab={setCurrentTab}
        wsStatus={wsStatus}
        lastUpdateUtc={lastUpdateUtc}
        onGenerateRoster={handleGenerateRoster}
        onResetDemo={handleResetDemo}
        isGenerating={isGenerating}
        isResetting={isResetting}
        eventCount={events.length}
        onToggleEventsDrawer={() => setIsEventsDrawerOpen(!isEventsDrawerOpen)}
        isEventsDrawerOpen={isEventsDrawerOpen}
      />

      {/* Floating Notification Toast */}
      {notification && (
        <div className="fixed top-16 right-4 z-50 animate-in fade-in slide-in-from-top duration-200">
          <div
            className={`px-4 py-2.5 rounded-lg border text-xs font-mono shadow-2xl flex items-center gap-2 ${
              notification.type === 'success'
                ? 'bg-emerald-950/90 text-emerald-300 border-emerald-700/80'
                : notification.type === 'error'
                ? 'bg-rose-950/90 text-rose-300 border-rose-700/80'
                : 'bg-cyan-950/90 text-cyan-300 border-cyan-700/80'
            }`}
          >
            <span>{notification.message}</span>
          </div>
        </div>
      )}

      {/* Main View Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8">
        {currentTab === 'overview' && (
          <OverviewView
            summary={summary}
            upcomingFlights={flights}
            onNavigate={setCurrentTab}
            isLoading={isLoading}
          />
        )}

        {currentTab === 'schedule' && (
          <FlightScheduleView
            flights={flights}
            btreeTelemetry={btreeTelemetry}
            onRefresh={loadData}
            isLoading={isLoading}
            onRescheduleFlight={handleRescheduleFlight}
            onCreateFlight={handleCreateFlight}
            onRangeSearch={handleRangeSearch}
          />
        )}

        {currentTab === 'roster' && (
          <RosterPlannerView
            flights={flights}
            crewList={crewList}
            aircraftList={aircraftList}
            onManualAssign={handleManualAssign}
          />
        )}

        {currentTab === 'crew' && (
          <CrewDirectoryView
            crewList={crewList}
          />
        )}

        {currentTab === 'fleet' && (
          <AircraftFleetView
            aircraftList={aircraftList}
            flights={flights}
          />
        )}

        {currentTab === 'constraints' && (
          <ConstraintInspectorView />
        )}

        {currentTab === 'disruptions' && (
          <DisruptionSimulatorView
            onRefreshAll={loadData}
          />
        )}

        {currentTab === 'laboratory' && (
          <ADSLaboratoryView />
        )}
      </main>

      {/* Live WebSocket Event Stream Drawer */}
      <EventDrawer
        isOpen={isEventsDrawerOpen}
        onClose={() => setIsEventsDrawerOpen(false)}
        events={events}
        onClear={clearEvents}
      />

      {/* Global Footer & Academic Integrity Notice */}
      <footer className="border-t border-slate-900 bg-slate-950/90 py-4 px-6 text-center text-xs text-slate-500 font-mono space-y-1">
        <div>
          AirCrewOps | Nova Air Operations Control System · Profile: <span className="text-cyan-400 font-semibold">nova_air_demo_v1</span>
        </div>
        <div className="text-[11px] text-slate-600">
          NMIMS MPSTME Advanced Data Structures (ADS) Course Simulator · Fail-Closed DGCA CAR Safety Model · Not Certified for Real-World Flight Operations
        </div>
      </footer>
    </div>
  );
}
