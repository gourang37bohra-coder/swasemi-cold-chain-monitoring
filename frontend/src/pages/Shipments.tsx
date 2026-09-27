import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Play, CheckCircle, Eye, Package, AlertCircle } from 'lucide-react';
import { shipmentsApi, trackersApi } from '../api/client';
import type { Shipment, ShipmentCreatePayload, Tracker } from '../types';
import { useAuth } from '../context/AuthContext';
import { StatusBadge } from '../components/StatusBadge';
import { Card } from '../components/Card';
import { Modal } from '../components/Modal';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { EmptyState } from '../components/EmptyState';

export const Shipments: React.FC = () => {
  const { isSuperAdmin } = useAuth();
  const [shipments, setShipments] = useState<Shipment[]>([]);
  const [trackers, setTrackers] = useState<Tracker[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create Modal state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [selectedTrackerId, setSelectedTrackerId] = useState('');
  const [minTemp, setMinTemp] = useState<number | string>(2.0);
  const [maxTemp, setMaxTemp] = useState<number | string>(8.0);
  const [graceReadings, setGraceReadings] = useState<number | string>(2);
  const [targetOrgId, setTargetOrgId] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Transition state
  const [transitioningId, setTransitioningId] = useState<string | null>(null);

  const fetchShipmentsAndTrackers = async (targetPage = page) => {
    try {
      setIsLoading(true);
      setError(null);
      const [shipmentsRes, trackersRes] = await Promise.all([
        shipmentsApi.list({ page: targetPage, page_size: pageSize }),
        trackersApi.list({ page_size: 100 }),
      ]);
      setShipments(shipmentsRes.items);
      setTotal(shipmentsRes.total);
      setPage(shipmentsRes.page);
      setTrackers(trackersRes.items);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch shipments');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchShipmentsAndTrackers(page);
  }, [page]);

  const handleOpenCreate = () => {
    if (trackers.length > 0) {
      setSelectedTrackerId(trackers[0].id);
    } else {
      setSelectedTrackerId('');
    }
    setMinTemp(2.0);
    setMaxTemp(8.0);
    setGraceReadings(2);
    setFormError(null);
    setIsCreateOpen(true);
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedTrackerId) {
      setFormError('A tracker must be selected for the shipment.');
      return;
    }

    const min = parseFloat(String(minTemp));
    const max = parseFloat(String(maxTemp));
    const grace = parseInt(String(graceReadings), 10);

    if (isNaN(min) || isNaN(max)) {
      setFormError('Please enter valid numeric temperatures.');
      return;
    }

    if (min >= max) {
      setFormError(`Minimum temperature (${min}°C) must be strictly less than maximum temperature (${max}°C).`);
      return;
    }

    if (isNaN(grace) || grace < 1) {
      setFormError('Grace readings must be at least 1.');
      return;
    }

    try {
      setIsSubmitting(true);
      setFormError(null);
      const payload: ShipmentCreatePayload = {
        tracker_id: selectedTrackerId,
        minimum_temperature: min,
        maximum_temperature: max,
        grace_readings: grace,
        ...(isSuperAdmin && targetOrgId ? { organization_id: targetOrgId.trim() } : {}),
      };
      await shipmentsApi.create(payload);
      setIsCreateOpen(false);
      fetchShipmentsAndTrackers(1);
    } catch (err: any) {
      setFormError(err?.response?.data?.detail || 'Failed to create shipment');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleStartShipment = async (shipmentId: string) => {
    try {
      setTransitioningId(shipmentId);
      await shipmentsApi.start(shipmentId);
      await fetchShipmentsAndTrackers(page);
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to start shipment');
    } finally {
      setTransitioningId(null);
    }
  };

  const handleCompleteShipment = async (shipmentId: string) => {
    try {
      setTransitioningId(shipmentId);
      await shipmentsApi.complete(shipmentId);
      await fetchShipmentsAndTrackers(page);
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to complete shipment');
    } finally {
      setTransitioningId(null);
    }
  };

  const getTrackerName = (trackerId: string) => {
    const t = trackers.find((item) => item.id === trackerId);
    return t ? t.name : trackerId.slice(0, 8);
  };

  const totalPages = Math.ceil(total / pageSize) || 1;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)' }}>Cold-Chain Shipments</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13.5px', marginTop: '2px' }}>
            Lifecycle tracking, temperature profiles, and sensor telemetry dispatch.
          </p>
        </div>
        <button onClick={handleOpenCreate} className="btn btn-primary">
          <Plus size={16} />
          <span>New Shipment</span>
        </button>
      </div>

      {error && (
        <div style={{ padding: '12px', borderRadius: '6px', backgroundColor: 'var(--danger-bg)', border: '1px solid var(--danger-border)', color: 'var(--danger)' }}>
          {error}
        </div>
      )}

      <Card>
        {isLoading ? (
          <LoadingSpinner label="Fetching shipments..." />
        ) : shipments.length === 0 ? (
          <EmptyState
            message="No shipments created yet."
            description="Create a shipment, assign an IoT tracker, and establish temperature thresholds."
            action={
              <button onClick={handleOpenCreate} className="btn btn-primary" style={{ fontSize: '13px' }}>
                <Plus size={14} /> Create Shipment
              </button>
            }
          />
        ) : (
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Shipment ID</th>
                  <th>Assigned Tracker</th>
                  <th>Lifecycle Status</th>
                  <th>Threshold Range</th>
                  <th>Grace Readings</th>
                  <th>Started At</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {shipments.map((s) => {
                  const isTransitioning = transitioningId === s.id;
                  return (
                    <tr key={s.id}>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <Package size={16} color="var(--primary)" />
                          <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>
                            {s.id.slice(0, 8)}...
                          </span>
                        </div>
                      </td>
                      <td>
                        <span style={{ fontWeight: 500, color: 'var(--text-main)' }}>
                          {getTrackerName(s.tracker_id)}
                        </span>
                      </td>
                      <td>
                        <StatusBadge status={s.status} />
                      </td>
                      <td>
                        <span style={{ fontWeight: 600 }}>
                          {s.minimum_temperature}°C to {s.maximum_temperature}°C
                        </span>
                      </td>
                      <td>{s.grace_readings}</td>
                      <td style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                        {s.started_at ? new Date(s.started_at).toLocaleString() : 'Not started'}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', gap: '8px', alignItems: 'center' }}>
                          {s.status === 'NOT_STARTED' && (
                            <button
                              disabled={isTransitioning}
                              onClick={() => handleStartShipment(s.id)}
                              className="btn btn-primary"
                              style={{ padding: '5px 12px', fontSize: '12px' }}
                            >
                              <Play size={13} />
                              <span>{isTransitioning ? 'Starting...' : 'Start'}</span>
                            </button>
                          )}

                          {s.status === 'ACTIVE' && (
                            <button
                              disabled={isTransitioning}
                              onClick={() => handleCompleteShipment(s.id)}
                              className="btn btn-secondary"
                              style={{ padding: '5px 12px', fontSize: '12px', color: 'var(--success)' }}
                            >
                              <CheckCircle size={13} />
                              <span>{isTransitioning ? 'Ending...' : 'End Shipment'}</span>
                            </button>
                          )}

                          <Link
                            to={`/shipments/${s.id}`}
                            className="btn btn-secondary"
                            style={{ padding: '5px 10px', fontSize: '12px' }}
                            title="Inspect shipment details"
                          >
                            <Eye size={13} />
                            <span>Details</span>
                          </Link>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {/* Pagination Controls */}
            <div className="pagination">
              <span>
                Showing page <strong>{page}</strong> of <strong>{totalPages}</strong> ({total} total shipments)
              </span>
              <div className="pagination-controls">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(p - 1, 1))}
                  className="btn btn-secondary"
                  style={{ padding: '6px 12px', fontSize: '12px' }}
                >
                  Previous
                </button>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
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

      {/* Create Shipment Modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Initialize New Shipment"
        footer={
          <>
            <button onClick={() => setIsCreateOpen(false)} className="btn btn-secondary">
              Cancel
            </button>
            <button
              onClick={handleCreateSubmit}
              disabled={isSubmitting || trackers.length === 0}
              className="btn btn-primary"
            >
              {isSubmitting ? 'Creating...' : 'Create Shipment'}
            </button>
          </>
        }
      >
        <form onSubmit={handleCreateSubmit}>
          {formError && (
            <div style={{ padding: '10px', borderRadius: '6px', backgroundColor: 'var(--danger-bg)', border: '1px solid var(--danger-border)', color: 'var(--danger)', marginBottom: '16px', fontSize: '13px' }}>
              {formError}
            </div>
          )}

          {trackers.length === 0 ? (
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center', color: 'var(--warning)', fontSize: '13px', marginBottom: '16px' }}>
              <AlertCircle size={18} />
              <span>No trackers registered in this organization. Register a tracker first.</span>
            </div>
          ) : (
            <div className="form-group">
              <label className="form-label">Assign Hardware Tracker</label>
              <select
                className="form-select"
                value={selectedTrackerId}
                onChange={(e) => setSelectedTrackerId(e.target.value)}
              >
                {trackers.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.status})
                  </option>
                ))}
              </select>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div className="form-group">
              <label className="form-label">Min Allowed Temp (°C)</label>
              <input
                type="number"
                step="0.1"
                required
                className="form-input"
                value={minTemp}
                onChange={(e) => setMinTemp(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Max Allowed Temp (°C)</label>
              <input
                type="number"
                step="0.1"
                required
                className="form-input"
                value={maxTemp}
                onChange={(e) => setMaxTemp(e.target.value)}
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Grace Readings (Violations tolerated before breach alert)</label>
            <input
              type="number"
              min="1"
              required
              className="form-input"
              value={graceReadings}
              onChange={(e) => setGraceReadings(e.target.value)}
            />
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              Must be at least 1 reading.
            </span>
          </div>

          {isSuperAdmin && (
            <div className="form-group">
              <label className="form-label">Target Organization ID (Optional for SUPER_ADMIN)</label>
              <input
                type="text"
                className="form-input"
                placeholder="Leave blank to infer from tracker"
                value={targetOrgId}
                onChange={(e) => setTargetOrgId(e.target.value)}
              />
            </div>
          )}
        </form>
      </Modal>
    </div>
  );
};
