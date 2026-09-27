import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  MapContainer,
  TileLayer,
  Polyline,
  Marker,
  Popup,
} from 'react-leaflet';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  CartesianGrid,
} from 'recharts';
import {
  ArrowLeft,
  Play,
  CheckCircle,
  Radio,
  Thermometer,
  Compass,
  Battery,
  Droplets,
  DoorOpen,
  Download,
  AlertTriangle,
  Clock,
  Activity,
} from 'lucide-react';
import { shipmentsApi, trackersApi } from '../api/client';
import type { Alert, Shipment, ShipmentMetrics, Telemetry, Tracker } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import { Card } from '../components/Card';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { EmptyState } from '../components/EmptyState';
import { createRoutePinIcon } from '../utils/leafletIcons';
import { useLiveTelemetry } from '../hooks/useLiveTelemetry';

export const ShipmentDetail: React.FC = () => {
  const { shipmentId } = useParams<{ shipmentId: string }>();
  const [shipment, setShipment] = useState<Shipment | null>(null);
  const [tracker, setTracker] = useState<Tracker | null>(null);
  const [metrics, setMetrics] = useState<ShipmentMetrics | null>(null);
  const [telemetry, setTelemetry] = useState<Telemetry[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  // Real-time live telemetry streaming for this shipment
  const handleLiveTelemetry = (newReading: Telemetry) => {
    setTelemetry((prev) => {
      if (prev.some((t) => t.id === newReading.id)) return prev;
      const updated = [...prev, newReading];
      return updated.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
    });
  };

  // Real-time live alert notification
  const handleLiveAlert = (newAlert: Alert) => {
    setAlerts((prev) => [newAlert, ...prev.filter((a) => a.id !== newAlert.id)]);
    setShipment((prev) => (prev ? { ...prev, breach_active: true } : prev));
  };

  const { isConnected } = useLiveTelemetry({
    shipmentId,
    onTelemetryReceived: handleLiveTelemetry,
    onAlertReceived: handleLiveAlert,
  });

  // Table pagination
  const [tablePage, setTablePage] = useState(1);
  const tablePageSize = 10;

  const loadData = async () => {
    if (!shipmentId) return;
    try {
      setIsLoading(true);
      setError(null);

      // Load shipment history with metrics, telemetry, and alerts
      const [historyData, trackerData, alertsData, telemData] = await Promise.all([
        shipmentsApi.getHistory(shipmentId),
        shipmentsApi.get(shipmentId).then((s) => trackersApi.get(s.tracker_id).catch(() => null)),
        shipmentsApi.getAlerts(shipmentId).catch(() => []),
        shipmentsApi.getTelemetry(shipmentId).catch(() => []),
      ]);

      setShipment(historyData.shipment);
      setMetrics(historyData.metrics);
      setTracker(trackerData);
      setAlerts(alertsData);
      setTelemetry(telemData);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load shipment details');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [shipmentId]);

  const handleStart = async () => {
    if (!shipment) return;
    try {
      setIsTransitioning(true);
      const updated = await shipmentsApi.start(shipment.id);
      setShipment(updated);
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to start shipment');
    } finally {
      setIsTransitioning(false);
    }
  };

  const handleComplete = async () => {
    if (!shipment) return;
    try {
      setIsTransitioning(true);
      const updated = await shipmentsApi.complete(shipment.id);
      setShipment(updated);
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to complete shipment');
    } finally {
      setIsTransitioning(false);
    }
  };

  const handleExportCsv = async () => {
    if (!shipment) return;
    try {
      setIsExporting(true);
      const blob = await shipmentsApi.exportCsv(shipment.id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `shipment_${shipment.id}_telemetry.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to export telemetry CSV');
    } finally {
      setIsExporting(false);
    }
  };

  const formatDuration = (seconds?: number | null) => {
    if (seconds == null || isNaN(seconds)) return '--';
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    if (hrs > 0) return `${hrs}h ${mins}m`;
    if (mins > 0) return `${mins}m ${secs}s`;
    return `${secs}s`;
  };

  if (isLoading) {
    return <LoadingSpinner label="Loading shipment monitoring telemetry..." />;
  }

  if (error || !shipment) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <Link to="/shipments" className="btn btn-secondary" style={{ width: 'fit-content' }}>
          <ArrowLeft size={16} /> Back to Shipments
        </Link>
        <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: 'var(--danger-bg)', border: '1px solid var(--danger-border)', color: 'var(--danger)' }}>
          {error || 'Shipment not found within your organization.'}
        </div>
      </div>
    );
  }

  // GPS coordinates trail
  const validCoordinates = telemetry
    .filter((t) => typeof t.latitude === 'number' && typeof t.longitude === 'number')
    .map((t) => [t.latitude, t.longitude] as [number, number]);

  const startCoord = validCoordinates.length > 0 ? validCoordinates[0] : null;
  const latestCoord = validCoordinates.length > 0 ? validCoordinates[validCoordinates.length - 1] : null;

  // Chart data formatting
  const chartData = telemetry.map((t) => ({
    time: new Date(t.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    temperature: t.temperature,
    humidity: t.humidity,
    battery: t.battery,
    door_status: t.door_status ? 'OPEN' : 'CLOSED',
    timestamp: t.timestamp,
    isBreached: t.temperature < shipment.minimum_temperature || t.temperature > shipment.maximum_temperature,
  }));

  // Table pagination slicing (telemetry is in chronological order; show newest first in table)
  const reversedForTable = [...telemetry].reverse();
  const paginatedTable = reversedForTable.slice(
    (tablePage - 1) * tablePageSize,
    tablePage * tablePageSize
  );
  const totalTablePages = Math.ceil(telemetry.length / tablePageSize) || 1;

  // Latest metrics
  const latestReading = telemetry.length > 0 ? telemetry[telemetry.length - 1] : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
      {/* Navigation & Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Link to="/shipments" className="btn btn-secondary" style={{ padding: '8px' }}>
            <ArrowLeft size={18} />
          </Link>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)' }}>
                Shipment {shipment.id.slice(0, 8)}
              </h1>
              <StatusBadge status={shipment.status} />
              {shipment.breach_active && <StatusBadge status="BREACH" />}
            </div>
            <p style={{ color: 'var(--text-muted)', fontSize: '13px', marginTop: '2px', fontFamily: 'monospace' }}>
              ID: {shipment.id}
            </p>
          </div>
        </div>

        {/* Action Buttons: Export CSV, Lifecycle Controls, Live Indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <button
            onClick={handleExportCsv}
            disabled={isExporting || telemetry.length === 0}
            className="btn btn-secondary"
            title="Download CSV containing all telemetry readings"
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <Download size={16} />
            <span>{isExporting ? 'Exporting...' : 'Export CSV'}</span>
          </button>

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

          {shipment.status === 'NOT_STARTED' && (
            <button
              onClick={handleStart}
              disabled={isTransitioning}
              className="btn btn-primary"
            >
              <Play size={16} />
              <span>{isTransitioning ? 'Starting...' : 'Start Shipment'}</span>
            </button>
          )}

          {shipment.status === 'ACTIVE' && (
            <button
              onClick={handleComplete}
              disabled={isTransitioning}
              className="btn btn-secondary"
              style={{ color: 'var(--success)', borderColor: 'var(--success-border)' }}
            >
              <CheckCircle size={16} />
              <span>{isTransitioning ? 'Ending...' : 'Complete Shipment'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Shipment Specs Grid */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-info">
            <span className="kpi-label">Assigned Tracker</span>
            <span className="kpi-value" style={{ fontSize: '18px' }}>
              {tracker ? tracker.name : shipment.tracker_id.slice(0, 8)}
            </span>
          </div>
          <div className="kpi-icon-wrapper">
            <Radio size={22} />
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-info">
            <span className="kpi-label">Allowed Temp Band</span>
            <span className="kpi-value" style={{ fontSize: '20px' }}>
              {shipment.minimum_temperature}°C ~ {shipment.maximum_temperature}°C
            </span>
          </div>
          <div className="kpi-icon-wrapper" style={{ color: 'var(--primary)' }}>
            <Thermometer size={22} />
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-info">
            <span className="kpi-label">Grace Readings</span>
            <span className="kpi-value">{shipment.grace_readings}</span>
          </div>
          <div className="kpi-icon-wrapper" style={{ color: 'var(--warning)' }}>
            <Compass size={22} />
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-info">
            <span className="kpi-label">Latest Temperature</span>
            <span className="kpi-value" style={{ color: latestReading ? (latestReading.temperature < shipment.minimum_temperature || latestReading.temperature > shipment.maximum_temperature ? 'var(--danger)' : 'var(--primary)') : 'var(--text-muted)' }}>
              {latestReading ? `${latestReading.temperature.toFixed(1)}°C` : '--'}
            </span>
          </div>
          <div className="kpi-icon-wrapper" style={{ color: 'var(--primary)' }}>
            <Thermometer size={22} />
          </div>
        </div>
      </div>

      {/* Historical Summary Statistics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px' }}>
        <div className="card" style={{ padding: '16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Activity size={22} color="var(--primary)" />
          <div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Total Readings</div>
            <div style={{ fontSize: '18px', fontWeight: 700 }}>{metrics?.reading_count ?? telemetry.length}</div>
          </div>
        </div>

        <div className="card" style={{ padding: '16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Clock size={22} color="var(--text-secondary)" />
          <div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Duration</div>
            <div style={{ fontSize: '18px', fontWeight: 700 }}>{formatDuration(metrics?.duration_seconds)}</div>
          </div>
        </div>

        <div className="card" style={{ padding: '16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Thermometer size={22} color="var(--success)" />
          <div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Min Observed</div>
            <div style={{ fontSize: '18px', fontWeight: 700 }}>
              {metrics?.min_temperature != null ? `${metrics.min_temperature.toFixed(1)}°C` : '--'}
            </div>
          </div>
        </div>

        <div className="card" style={{ padding: '16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Thermometer size={22} color="var(--danger)" />
          <div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Max Observed</div>
            <div style={{ fontSize: '18px', fontWeight: 700 }}>
              {metrics?.max_temperature != null ? `${metrics.max_temperature.toFixed(1)}°C` : '--'}
            </div>
          </div>
        </div>

        <div className="card" style={{ padding: '16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Thermometer size={22} color="var(--warning)" />
          <div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Average Temp</div>
            <div style={{ fontSize: '18px', fontWeight: 700 }}>
              {metrics?.avg_temperature != null ? `${metrics.avg_temperature.toFixed(1)}°C` : '--'}
            </div>
          </div>
        </div>
      </div>

      {/* Live Sensors Row if readings exist */}
      {latestReading && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px' }}>
          <div className="card" style={{ padding: '16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Droplets size={22} color="var(--primary)" />
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Humidity</div>
              <div style={{ fontSize: '18px', fontWeight: 700 }}>{latestReading.humidity.toFixed(1)}%</div>
            </div>
          </div>

          <div className="card" style={{ padding: '16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Battery size={22} color="var(--success)" />
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Battery</div>
              <div style={{ fontSize: '18px', fontWeight: 700 }}>{latestReading.battery.toFixed(0)}%</div>
            </div>
          </div>

          <div className="card" style={{ padding: '16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
            <DoorOpen size={22} color={latestReading.door_status ? 'var(--danger)' : 'var(--success)'} />
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Door Status</div>
              <div style={{ fontSize: '18px', fontWeight: 700 }}>{latestReading.door_status ? 'OPEN' : 'CLOSED'}</div>
            </div>
          </div>
        </div>
      )}

      {/* Temperature Time-Series Chart */}
      <Card title="Temperature Profile History (°C)">
        {chartData.length === 0 ? (
          <EmptyState
            message="No temperature telemetry recorded yet."
            description="Telemetry is recorded and persisted exclusively while the shipment is in ACTIVE status."
          />
        ) : (
          <div style={{ height: '340px', width: '100%', marginTop: '12px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis
                  dataKey="time"
                  stroke="#64748B"
                  fontSize={12}
                  tickLine={false}
                />
                <YAxis
                  stroke="#64748B"
                  fontSize={12}
                  tickLine={false}
                  unit="°C"
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload;
                      return (
                        <div
                          style={{
                            backgroundColor: '#FFFFFF',
                            border: `1px solid ${data.isBreached ? '#D9534F' : '#CBD5E1'}`,
                            borderRadius: '6px',
                            boxShadow: '0 4px 12px rgba(23, 32, 51, 0.08)',
                            padding: '10px 14px',
                            color: '#172033',
                            fontSize: '13px',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '4px',
                          }}
                        >
                          <div style={{ fontWeight: 600, color: data.isBreached ? '#D9534F' : '#2F80C0' }}>
                            {data.temperature.toFixed(2)} °C {data.isBreached && '(BREACH)'}
                          </div>
                          <div style={{ color: '#64748B', fontSize: '12px' }}>
                            Time: {new Date(data.timestamp).toLocaleString()}
                          </div>
                          <div style={{ color: '#64748B', fontSize: '12px' }}>
                            Humidity: {data.humidity.toFixed(1)}% | Battery: {data.battery.toFixed(0)}%
                          </div>
                          <div style={{ color: '#64748B', fontSize: '12px' }}>
                            Door: {data.door_status}
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                {/* Safe Temperature Threshold Lines */}
                <ReferenceLine
                  y={shipment.maximum_temperature}
                  stroke="#D9534F"
                  strokeDasharray="4 4"
                  label={{ value: `Max: ${shipment.maximum_temperature}°C`, fill: '#D9534F', fontSize: 11 }}
                />
                <ReferenceLine
                  y={shipment.minimum_temperature}
                  stroke="#2F80C0"
                  strokeDasharray="4 4"
                  label={{ value: `Min: ${shipment.minimum_temperature}°C`, fill: '#2F80C0', fontSize: 11 }}
                />
                <Line
                  type="monotone"
                  dataKey="temperature"
                  stroke="#2F80C0"
                  strokeWidth={2.5}
                  dot={{ r: 3, fill: '#2F80C0' }}
                  activeDot={{ r: 6 }}
                  name="Temperature"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      {/* GPS Trail Map */}
      <Card title="GPS Route Trail">
        <div style={{ height: '380px', width: '100%', position: 'relative' }}>
          {validCoordinates.length === 0 ? (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <EmptyState
                message="No GPS history available."
                description="Coordinates will appear as telemetry is received during transit."
              />
            </div>
          ) : (
            <MapContainer
              center={latestCoord || startCoord!}
              zoom={7}
              scrollWheelZoom={false}
              style={{ height: '100%', width: '100%' }}
            >
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              <Polyline
                positions={validCoordinates}
                color="#2F80C0"
                weight={4}
                opacity={0.8}
              />
              {startCoord && (
                <Marker position={startCoord} icon={createRoutePinIcon('start')}>
                  <Popup>
                    <strong>Origin Position (Point A)</strong>
                    <br />
                    Lat: {startCoord[0].toFixed(4)}, Lon: {startCoord[1].toFixed(4)}
                  </Popup>
                </Marker>
              )}
              {latestCoord && (
                <Marker position={latestCoord} icon={createRoutePinIcon('end')}>
                  <Popup>
                    <strong>Current / Destination (Point B)</strong>
                    <br />
                    Lat: {latestCoord[0].toFixed(4)}, Lon: {latestCoord[1].toFixed(4)}
                  </Popup>
                </Marker>
              )}
            </MapContainer>
          )}
        </div>
      </Card>

      {/* Compliance Alerts Section */}
      <Card title={`Compliance Breach Alerts (${alerts.length})`}>
        {alerts.length === 0 ? (
          <EmptyState
            message="No temperature breaches recorded."
            description="All sensor readings have remained compliant within the configured temperature profile."
          />
        ) : (
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Alert Type</th>
                  <th>Triggered At (UTC)</th>
                  <th>Observed Temp</th>
                  <th>Message</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((alert) => (
                  <tr key={alert.id}>
                    <td>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                          color: '#ef4444',
                          fontWeight: 600,
                          fontSize: '13px',
                        }}
                      >
                        <AlertTriangle size={15} />
                        {alert.type}
                      </span>
                    </td>
                    <td style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                      {new Date(alert.triggered_at).toLocaleString()}
                    </td>
                    <td style={{ fontWeight: 700, color: '#dc2626' }}>
                      {alert.temperature != null ? `${alert.temperature.toFixed(2)}°C` : '--'}
                    </td>
                    <td style={{ fontSize: '13px', color: 'var(--text-main)' }}>{alert.message}</td>
                    <td>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 600,
                          padding: '2px 8px',
                          borderRadius: '4px',
                          backgroundColor: alert.resolved_at ? 'var(--success-bg)' : 'var(--danger-bg)',
                          color: alert.resolved_at ? 'var(--success)' : 'var(--danger)',
                        }}
                      >
                        {alert.resolved_at ? 'RESOLVED' : 'ACTIVE'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Telemetry Log Table */}
      <Card title={`Sensor Reading History (${telemetry.length} records)`}>
        {telemetry.length === 0 ? (
          <EmptyState
            message="No sensor readings available."
            description="Active shipments ingest sensor data over MQTT."
          />
        ) : (
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Timestamp (UTC)</th>
                  <th>Temperature</th>
                  <th>Humidity</th>
                  <th>Battery</th>
                  <th>Door Status</th>
                  <th>GPS Coordinates</th>
                </tr>
              </thead>
              <tbody>
                {paginatedTable.map((t) => (
                  <tr key={t.id}>
                    <td style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                      {new Date(t.timestamp).toLocaleString()}
                    </td>
                    <td>
                      <span
                        style={{
                          fontWeight: 700,
                          color:
                            t.temperature < shipment.minimum_temperature ||
                            t.temperature > shipment.maximum_temperature
                              ? '#dc2626'
                              : 'var(--text-main)',
                        }}
                      >
                        {t.temperature.toFixed(2)}°C
                      </span>
                    </td>
                    <td>{t.humidity.toFixed(1)}%</td>
                    <td>{t.battery.toFixed(0)}%</td>
                    <td>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 600,
                          padding: '2px 6px',
                          borderRadius: '4px',
                          backgroundColor: t.door_status ? 'var(--danger-bg)' : 'var(--success-bg)',
                          color: t.door_status ? 'var(--danger)' : 'var(--success)',
                        }}
                      >
                        {t.door_status ? 'OPEN' : 'CLOSED'}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'monospace', fontSize: '12px', color: 'var(--text-muted)' }}>
                      {t.latitude.toFixed(4)}, {t.longitude.toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Table pagination */}
            <div className="pagination">
              <span>
                Page <strong>{tablePage}</strong> of <strong>{totalTablePages}</strong> ({telemetry.length} readings)
              </span>
              <div className="pagination-controls">
                <button
                  disabled={tablePage <= 1}
                  onClick={() => setTablePage((p) => Math.max(p - 1, 1))}
                  className="btn btn-secondary"
                  style={{ padding: '6px 12px', fontSize: '12px' }}
                >
                  Previous
                </button>
                <button
                  disabled={tablePage >= totalTablePages}
                  onClick={() => setTablePage((p) => p + 1)}
                  className="btn btn-secondary"
                  style={{ padding: '6px 12px', fontSize: '12px' }}
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
};
