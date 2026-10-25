/**
 * AirCrewOps — Centralized Runtime Configuration
 *
 * Provides configurable base endpoints for REST API and WebSocket operations
 * with robust local development defaults connecting directly to port 8000,
 * independently of whether Vite runs on port 3000, 3001, or 5173.
 */

const getBackendHost = (): string => {
  // Explicit env override if set
  if (import.meta.env.VITE_BACKEND_HOST) {
    return import.meta.env.VITE_BACKEND_HOST;
  }
  // Default to same host as browser, targeting backend port 8000
  const hostname = (typeof window !== 'undefined' && window.location.hostname) || 'localhost';
  return `${hostname}:8000`;
};

// Base HTTP URL for API requests
export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? `http://${getBackendHost()}/api/v1` : '/api/v1');

// Base WebSocket URL for real-time operations
export const WS_URL: string =
  import.meta.env.VITE_WS_URL ||
  (import.meta.env.DEV
    ? `ws://${getBackendHost()}/ws/operations`
    : `${typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${getBackendHost()}/ws/operations`);
