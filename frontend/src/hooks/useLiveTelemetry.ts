import { useEffect, useRef, useState, useCallback } from 'react';
import { telemetryApi } from '../api/client';
import type { Alert, Telemetry } from '../types';

interface UseLiveTelemetryOptions {
  trackerId?: string;
  shipmentId?: string;
  onTelemetryReceived?: (telemetry: Telemetry) => void;
  onAlertReceived?: (alert: Alert) => void;
}

/**
 * Hook providing live telemetry via REST bootstrap + WebSocket real-time event updates.
 *
 * Implements exponential backoff auto-reconnection (1s, 2s, 4s, 8s, max 16s),
 * token refresh on reconnect, and keepalive heartbeats.
 */
export function useLiveTelemetry(options?: UseLiveTelemetryOptions) {
  const [telemetry, setTelemetry] = useState<Telemetry[]>([]);
  const [latestTelemetry, setLatestTelemetry] = useState<Telemetry | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectDelayRef = useRef<number>(1000); // Start at 1s
  const isMountedRef = useRef<boolean>(true);

  // Keep latest callback ref without triggering reconnects
  const onReceivedRef = useRef(options?.onTelemetryReceived);
  const onAlertReceivedRef = useRef(options?.onAlertReceived);
  useEffect(() => {
    onReceivedRef.current = options?.onTelemetryReceived;
    onAlertReceivedRef.current = options?.onAlertReceived;
  }, [options?.onTelemetryReceived, options?.onAlertReceived]);

  // Initial REST Bootstrap
  const fetchHistorical = useCallback(async () => {
    try {
      setIsLoading(true);
      const res = await telemetryApi.list({
        tracker_id: options?.trackerId,
        shipment_id: options?.shipmentId,
        page_size: 100,
      });
      if (isMountedRef.current) {
        setTelemetry(res.items);
        setLatestTelemetry(res.items.length > 0 ? res.items[0] : null);
        setError(null);
      }
    } catch (err: any) {
      if (isMountedRef.current) {
        setError(err?.response?.data?.detail || 'Failed to load telemetry history');
      }
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
      }
    }
  }, [options?.trackerId, options?.shipmentId]);

  // WebSocket Connection Lifecycle
  const connectWebSocket = useCallback(() => {
    if (!isMountedRef.current) return;

    const token = localStorage.getItem('token');
    if (!token) {
      setIsConnected(false);
      return;
    }

    const apiUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
    const wsBaseUrl = apiUrl.replace(/^http/, 'ws');
    const wsUrl = `${wsBaseUrl}/ws/telemetry?token=${encodeURIComponent(token)}`;

    try {
      const ws = new WebSocket(wsUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        if (!isMountedRef.current) return;
        setIsConnected(true);
        reconnectDelayRef.current = 1000; // Reset backoff on successful connect

        // Start heartbeat ping every 30 seconds
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30000);
      };

      ws.onmessage = (event) => {
        if (!isMountedRef.current) return;
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'telemetry.updated' && payload.data) {
            const newReading: Telemetry = payload.data;

            // Filter by trackerId or shipmentId if specified
            if (options?.trackerId && newReading.tracker_id !== options.trackerId) {
              return;
            }
            if (options?.shipmentId && newReading.shipment_id !== options.shipmentId) {
              return;
            }

            // Update live state
            setLatestTelemetry(newReading);
            setTelemetry((prev) => {
              const filtered = prev.filter((t) => t.id !== newReading.id);
              return [newReading, ...filtered];
            });

            onReceivedRef.current?.(newReading);
          } else if (payload.type === 'alert.triggered' && payload.data) {
            const newAlert: Alert = payload.data;
            if (options?.shipmentId && newAlert.shipment_id !== options.shipmentId) {
              return;
            }
            if (options?.trackerId && newAlert.tracker_id !== options.trackerId) {
              return;
            }
            onAlertReceivedRef.current?.(newAlert);
          }
        } catch {
          // Ignore parse errors or non-json keepalive frames
        }
      };

      ws.onclose = () => {
        if (!isMountedRef.current) return;
        setIsConnected(false);
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);

        // Exponential backoff reconnect: 1s, 2s, 4s, 8s, max 16s
        const nextDelay = Math.min(reconnectDelayRef.current, 16000);
        reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 2, 16000);

        reconnectTimeoutRef.current = setTimeout(() => {
          if (isMountedRef.current) {
            connectWebSocket();
          }
        }, nextDelay);
      };

      ws.onerror = () => {
        // Socket close event will handle reconnect logic
        ws.close();
      };
    } catch {
      // Reconnect after delay
      reconnectTimeoutRef.current = setTimeout(connectWebSocket, 5000);
    }
  }, [options?.trackerId, options?.shipmentId]);

  useEffect(() => {
    isMountedRef.current = true;
    fetchHistorical();
    connectWebSocket();

    return () => {
      isMountedRef.current = false;
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
      if (socketRef.current) {
        socketRef.current.close();
      }
    };
  }, [fetchHistorical, connectWebSocket]);

  return {
    telemetry,
    latestTelemetry,
    isConnected,
    isLoading,
    error,
    refresh: fetchHistorical,
  };
}
