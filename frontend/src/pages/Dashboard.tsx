import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import { Package, Radio, CheckCircle2, AlertCircle, Thermometer, Clock } from 'lucide-react';
import { shipmentsApi, telemetryApi, trackersApi } from '../api/client';
import type { Shipment, Telemetry, Tracker } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { EmptyState } from '../components/EmptyState';
import { createTrackerMarkerIcon } from '../utils/leafletIcons';
import { useLiveTelemetry } from '../hooks/useLiveTelemetry';

interface TrackerWithTelemetry {
  tracker: Tracker;
  latestTelemetry?: Telemetry;
}

/**
 * Automatically fits map bounds to include all active tracker coordinates.
 * If 2 or more markers exist, adjusts viewport with padding.
 * If only 1 marker exists, pans and zooms centered on that marker.
 */
const MapBoundsUpdater: React.FC<{ markers: TrackerWithTelemetry[] }> = ({ markers }) => {
  const map = useMap();

  useEffect(() => {
    if (markers.length >= 2) {
      const bounds = L.latLngBounds(
        markers.map((m) => [m.latestTelemetry!.latitude, m.latestTelemetry!.longitude])
      );
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 12 });
    } else if (markers.length === 1) {
      const single = markers[0].latestTelemetry!;
      map.setView([single.latitude, single.longitude], 8);
    }
  }, [markers, map]);

  return null;
};

export const Dashboard: React.FC = () => {
  const [trackers, setTrackers] = useState<Tracker[]>([]);
  const [shipments, setShipments] = useState<Shipment[]>([]);
  const [latestReadings, setLatestReadings] = useState<Telemetry[]>([]);
  const [trackerMapData, setTrackerMapData] = useState<TrackerWithTelemetry[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Real-time telemetry receiver via WebSocket
  const handleRealtimeReading = (reading: Telemetry) => {
    // 1. Update latest readings array
    setLatestReadings((prev) => [reading, ...prev.filter((t) => t.id !== reading.id)]);

    // 2. Update tracker map data with new GPS coordinate & online state
    setTrackerMapData((prev) =>
      prev.map((item) => {
        if (item.tracker.id === reading.tracker_id) {
          return {
            ...item,
            tracker: {
              ...item.tracker,
              status: 'ONLINE',
              last_seen: reading.timestamp,
            },
            latestTelemetry: reading,
          };
        }
        return item;
      })
    );

    // 3. Mark tracker as ONLINE in trackers list
    setTrackers((prev) =>
      prev.map((t) =>
        t.id === reading.tracker_id
          ? { ...t, status: 'ONLINE', last_seen: reading.timestamp }
          : t
      )
    );
  };

  const { isConnected } = useLiveTelemetry({ onTelemetryReceived: handleRealtimeReading });

  useEffect(() => {
    const loadDashboardData = async () => {
      try {
        setIsLoading(true);
        // 1. Fetch trackers and shipments
        const [trackersRes, shipmentsRes] = await Promise.all([
          trackersApi.list({ page_size: 100 }),
          shipmentsApi.list({ page_size: 100 }),
        ]);

        const trackersList = trackersRes.items;
        setTrackers(trackersList);
        setShipments(shipmentsRes.items);

        // 2. Fetch the latest telemetry record for EACH tracker reliably using tracker_id filter
        const telemetryResults = await Promise.all(
          trackersList.map(async (tracker) => {
            try {
              const res = await telemetryApi.list({ tracker_id: tracker.id, page_size: 1 });
              return {
                tracker,
                latestTelemetry: res.items.length > 0 ? res.items[0] : undefined,
              };
            } catch {
              return {
                tracker,
                latestTelemetry: undefined,
              };
            }
          })
        );

        setTrackerMapData(telemetryResults);

        // Collect all retrieved readings into latestReadings sorted by timestamp desc
        const allLatest = telemetryResults
          .map((item) => item.latestTelemetry)
          .filter((t): t is Telemetry => Boolean(t))
          .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

        setLatestReadings(allLatest);
      } catch (err) {
        console.error('Failed to load dashboard metrics', err);
      } finally {
        setIsLoading(false);
      }
    };

    loadDashboardData();
  }, []);

  if (isLoading) {
    return <LoadingSpinner label="Loading cold-chain operations dashboard..." />;
  }

  // Calculate KPIs
  const activeShipmentsCount = shipments.filter((s) => s.status === 'ACTIVE').length;
  const activeTrackersCount = trackers.length;
  const onlineTrackersCount = trackers.filter((t) => t.status === 'ONLINE').length;
  const offlineTrackersCount = trackers.filter((t) => t.status === 'OFFLINE').length;

  const latestTelemetryItem = latestReadings.length > 0 ? latestReadings[0] : null;
  const latestTempDisplay = latestTelemetryItem ? `${latestTelemetryItem.temperature.toFixed(1)}°C` : '--';
  const latestTimeDisplay = latestTelemetryItem
    ? new Date(latestTelemetryItem.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : 'No data';

  // Extract markers with valid coordinates
  const markersWithCoords = trackerMapData.filter(
    (item) => item.latestTelemetry && typeof item.latestTelemetry.latitude === 'number'
  );

  const defaultCenter: [number, number] = markersWithCoords.length > 0
    ? [markersWithCoords[0].latestTelemetry!.latitude, markersWithCoords[0].latestTelemetry!.longitude]
    : [20.5937, 78.9629]; // Default center

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
      {/* Page Title & Live WebSocket Indicator */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)' }}>Operations Command Center</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13.5px', marginTop: '2px' }}>
            Real-time cold-chain assets, temperature monitoring, and active fleet status.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '5px 12px',
              borderRadius: '6px',
              fontSize: '12px',
              fontWeight: 600,
              backgroundColor: isConnected ? '#EAF8F1' : '#F4F7FA',
              color: isConnected ? '#2E9B68' : '#64748B',
              border: `1px solid ${isConnected ? '#B7E4CD' : '#CBD5E1'}`,
            }}
          >
            <span
              style={{
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                backgroundColor: isConnected ? '#2E9B68' : '#64748B',
              }}
            />
            {isConnected ? 'LIVE WEBSOCKET' : 'CONNECTING'}
          </span>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-info">
            <span className="kpi-label">Active Shipments</span>
            <span className="kpi-value">{activeShipmentsCount}</span>
          </div>
          <div className="kpi-icon-wrapper" style={{ color: '#2F80C0', backgroundColor: '#EAF4FC', borderColor: '#BCD9F1' }}>
            <Package size={22} />
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-info">
            <span className="kpi-label">Active Trackers</span>
            <span className="kpi-value">{activeTrackersCount}</span>
          </div>
          <div className="kpi-icon-wrapper" style={{ color: '#2F80C0', backgroundColor: '#EAF4FC', borderColor: '#BCD9F1' }}>
            <Radio size={22} />
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-info">
            <span className="kpi-label">Online Units</span>
            <span className="kpi-value" style={{ color: '#2E9B68' }}>{onlineTrackersCount}</span>
          </div>
          <div className="kpi-icon-wrapper" style={{ color: '#2E9B68', backgroundColor: '#EAF8F1', borderColor: '#B7E4CD' }}>
            <CheckCircle2 size={22} />
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-info">
            <span className="kpi-label">Offline Units</span>
            <span className="kpi-value" style={{ color: offlineTrackersCount > 0 ? '#D99A22' : 'var(--text-main)' }}>{offlineTrackersCount}</span>
          </div>
          <div className="kpi-icon-wrapper" style={{ color: offlineTrackersCount > 0 ? '#D99A22' : '#64748B', backgroundColor: offlineTrackersCount > 0 ? '#FEF7E8' : '#F4F7FA', borderColor: offlineTrackersCount > 0 ? '#F7DC9F' : 'var(--border-secondary)' }}>
            <AlertCircle size={22} />
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-info">
            <span className="kpi-label">Latest Temp</span>
            <span className="kpi-value">{latestTempDisplay}</span>
          </div>
          <div className="kpi-icon-wrapper" style={{ color: '#2F80C0', backgroundColor: '#EAF4FC', borderColor: '#BCD9F1' }}>
            <Thermometer size={22} />
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-info">
            <span className="kpi-label">Latest Telemetry</span>
            <span className="kpi-value" style={{ fontSize: '18px' }}>{latestTimeDisplay}</span>
          </div>
          <div className="kpi-icon-wrapper" style={{ color: '#64748B', backgroundColor: '#F4F7FA', borderColor: 'var(--border-secondary)' }}>
            <Clock size={22} />
          </div>
        </div>
      </div>

      {/* Map Section - Primary Visual Element */}
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">Live Asset Fleet Map</h2>
          <span style={{ fontSize: '12.5px', color: 'var(--text-muted)' }}>
            {markersWithCoords.length} tracker(s) reporting location
          </span>
        </div>
        <div style={{ height: '500px', width: '100%', position: 'relative' }}>
          {markersWithCoords.length === 0 ? (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <EmptyState
                message="No active telemetry available."
                description="When trackers emit telemetry during active shipments, positions will appear on the map."
              />
            </div>
          ) : (
            <MapContainer
              center={defaultCenter}
              zoom={6}
              scrollWheelZoom={false}
              style={{ height: '100%', width: '100%' }}
            >
              <MapBoundsUpdater markers={markersWithCoords} />
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              {markersWithCoords.map(({ tracker, latestTelemetry }) => (
                <Marker
                  key={tracker.id}
                  position={[latestTelemetry!.latitude, latestTelemetry!.longitude]}
                  icon={createTrackerMarkerIcon(tracker.status)}
                >
                  <Popup>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      <strong style={{ fontSize: '14px', color: '#172033' }}>{tracker.name}</strong>
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <StatusBadge status={tracker.status} />
                        <span style={{ fontSize: '13px', fontWeight: 600, color: '#2F80C0' }}>
                          {latestTelemetry!.temperature.toFixed(1)}°C
                        </span>
                      </div>
                      <div style={{ fontSize: '12px', color: '#64748B' }}>
                        GPS: {latestTelemetry!.latitude.toFixed(4)}, {latestTelemetry!.longitude.toFixed(4)}
                      </div>
                      <div style={{ fontSize: '11px', color: '#64748B' }}>
                        Updated: {new Date(latestTelemetry!.timestamp).toLocaleString()}
                      </div>
                    </div>
                  </Popup>
                </Marker>
              ))}
            </MapContainer>
          )}
        </div>
      </div>

      {/* Recent Shipments Overview */}
      <div className="card">
        <div className="card-header">
          <h2 className="card-title">Active & Recent Shipments</h2>
          <Link to="/shipments" className="btn btn-secondary" style={{ fontSize: '12px', padding: '6px 12px' }}>
            View All Shipments
          </Link>
        </div>
        <div className="table-responsive">
          {shipments.length === 0 ? (
            <EmptyState
              message="No shipments found."
              description="Create a shipment and assign a tracker to begin temperature monitoring."
              action={
                <Link to="/shipments" className="btn btn-primary" style={{ fontSize: '13px' }}>
                  Create Shipment
                </Link>
              }
            />
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Shipment ID</th>
                  <th>Status</th>
                  <th>Allowed Temp Range</th>
                  <th>Grace Readings</th>
                  <th>Started At</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {shipments.slice(0, 5).map((shipment) => (
                  <tr key={shipment.id}>
                    <td style={{ fontFamily: 'monospace', fontSize: '13px' }}>
                      {shipment.id.slice(0, 8)}...
                    </td>
                    <td>
                      <StatusBadge status={shipment.status} />
                    </td>
                    <td>
                      <span style={{ fontWeight: 600 }}>
                        {shipment.minimum_temperature}°C to {shipment.maximum_temperature}°C
                      </span>
                    </td>
                    <td>{shipment.grace_readings}</td>
                    <td>
                      {shipment.started_at ? new Date(shipment.started_at).toLocaleString() : '--'}
                    </td>
                    <td>
                      <Link
                        to={`/shipments/${shipment.id}`}
                        className="btn btn-secondary"
                        style={{ fontSize: '12px', padding: '4px 10px' }}
                      >
                        Inspect
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
};
