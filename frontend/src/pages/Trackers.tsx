import React, { useEffect, useState } from 'react';
import { Plus, Edit2, Trash2, Radio, AlertTriangle } from 'lucide-react';
import { trackersApi } from '../api/client';
import type { Tracker, TrackerCreatePayload, TrackerStatus } from '../types';
import { useAuth } from '../context/AuthContext';
import { StatusBadge } from '../components/StatusBadge';
import { Card } from '../components/Card';
import { Modal } from '../components/Modal';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { EmptyState } from '../components/EmptyState';

export const Trackers: React.FC = () => {
  const { isSuperAdmin, user } = useAuth();
  const [trackers, setTrackers] = useState<Tracker[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal states
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingTracker, setEditingTracker] = useState<Tracker | null>(null);
  const [deletingTracker, setDeletingTracker] = useState<Tracker | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Form states
  const [name, setName] = useState('');
  const [mqttTopic, setMqttTopic] = useState('');
  const [status, setStatus] = useState<TrackerStatus>('OFFLINE');
  const [targetOrgId, setTargetOrgId] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const fetchTrackers = async (targetPage = page) => {
    try {
      setIsLoading(true);
      setError(null);
      const res = await trackersApi.list({ page: targetPage, page_size: pageSize });
      setTrackers(res.items);
      setTotal(res.total);
      setPage(res.page);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch trackers');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTrackers(page);
  }, [page]);

  const handleOpenCreate = () => {
    setName('');
    setMqttTopic(`coldchain/trackers/${user?.organization_id || 'org'}/telemetry`);
    setStatus('OFFLINE');
    setTargetOrgId(user?.organization_id || '');
    setFormError(null);
    setIsCreateOpen(true);
  };

  const handleOpenEdit = (tracker: Tracker) => {
    setEditingTracker(tracker);
    setName(tracker.name);
    setMqttTopic(tracker.mqtt_topic);
    setStatus(tracker.status);
    setFormError(null);
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !mqttTopic.trim()) {
      setFormError('Name and MQTT Topic are required.');
      return;
    }
    if (isSuperAdmin && !targetOrgId.trim()) {
      setFormError('organization_id is required for SUPER_ADMIN.');
      return;
    }

    try {
      setIsSubmitting(true);
      setFormError(null);
      const payload: TrackerCreatePayload = {
        name: name.trim(),
        mqtt_topic: mqttTopic.trim(),
        status,
        ...(isSuperAdmin && targetOrgId ? { organization_id: targetOrgId.trim() } : {}),
      };
      await trackersApi.create(payload);
      setIsCreateOpen(false);
      fetchTrackers(1);
    } catch (err: any) {
      setFormError(err?.response?.data?.detail || 'Failed to create tracker');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingTracker) return;
    if (!name.trim() || !mqttTopic.trim()) {
      setFormError('Name and MQTT Topic are required.');
      return;
    }

    try {
      setIsSubmitting(true);
      setFormError(null);
      await trackersApi.update(editingTracker.id, {
        name: name.trim(),
        mqtt_topic: mqttTopic.trim(),
        status,
      });
      setEditingTracker(null);
      fetchTrackers(page);
    } catch (err: any) {
      setFormError(err?.response?.data?.detail || 'Failed to update tracker');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!deletingTracker) return;
    try {
      setIsSubmitting(true);
      setDeleteError(null);
      await trackersApi.delete(deletingTracker.id);
      setDeletingTracker(null);
      fetchTrackers(page);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Failed to delete tracker';
      setDeleteError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const totalPages = Math.ceil(total / pageSize) || 1;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-main)' }}>IoT Fleet Trackers</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13.5px', marginTop: '2px' }}>
            Hardware GPS/sensor tracking units registered to your organization.
          </p>
        </div>
        <button onClick={handleOpenCreate} className="btn btn-primary">
          <Plus size={16} />
          <span>Register Tracker</span>
        </button>
      </div>

      {error && (
        <div style={{ padding: '12px', borderRadius: '6px', backgroundColor: 'var(--danger-bg)', border: '1px solid var(--danger-border)', color: 'var(--danger)' }}>
          {error}
        </div>
      )}

      <Card>
        {isLoading ? (
          <LoadingSpinner label="Fetching trackers..." />
        ) : trackers.length === 0 ? (
          <EmptyState
            message="No trackers registered yet."
            description="Add your first cold-chain tracker to monitor temperature and location."
            action={
              <button onClick={handleOpenCreate} className="btn btn-primary" style={{ fontSize: '13px' }}>
                <Plus size={14} /> Register Tracker
              </button>
            }
          />
        ) : (
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Tracker Name</th>
                  <th>MQTT Topic</th>
                  <th>Status</th>
                  <th>Last Seen</th>
                  {isSuperAdmin && <th>Organization</th>}
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {trackers.map((t) => (
                  <tr key={t.id}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <div style={{ color: 'var(--primary)' }}>
                          <Radio size={16} />
                        </div>
                        <div>
                          <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>{t.name}</div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                            {t.id}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <code style={{ fontSize: '12px', color: 'var(--text-main)', backgroundColor: 'var(--bg-main)', border: '1px solid var(--border)', padding: '2px 6px', borderRadius: '4px' }}>
                        {t.mqtt_topic}
                      </code>
                    </td>
                    <td>
                      <StatusBadge status={t.status} />
                    </td>
                    <td style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                      {t.last_seen ? new Date(t.last_seen).toLocaleString() : 'Never'}
                    </td>
                    {isSuperAdmin && (
                      <td style={{ fontSize: '12px', fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                        {t.organization_id.slice(0, 8)}...
                      </td>
                    )}
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '6px' }}>
                        <button
                          onClick={() => handleOpenEdit(t)}
                          className="btn btn-secondary"
                          style={{ padding: '6px' }}
                          title="Edit tracker"
                        >
                          <Edit2 size={15} />
                        </button>
                        <button
                          onClick={() => {
                            setDeletingTracker(t);
                            setDeleteError(null);
                          }}
                          className="btn btn-secondary"
                          style={{ padding: '6px', color: 'var(--danger)', borderColor: 'var(--danger-border)' }}
                          title="Delete tracker"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination Controls */}
            <div className="pagination">
              <span>
                Showing page <strong>{page}</strong> of <strong>{totalPages}</strong> ({total} total units)
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

      {/* Create Tracker Modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Register New Cold-Chain Tracker"
        footer={
          <>
            <button onClick={() => setIsCreateOpen(false)} className="btn btn-secondary">
              Cancel
            </button>
            <button onClick={handleCreateSubmit} disabled={isSubmitting} className="btn btn-primary">
              {isSubmitting ? 'Registering...' : 'Register'}
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
          <div className="form-group">
            <label className="form-label">Tracker Name</label>
            <input
              type="text"
              required
              className="form-input"
              placeholder="e.g. PharmaBox-Unit-A"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label">MQTT Telemetry Topic</label>
            <input
              type="text"
              required
              className="form-input"
              placeholder="coldchain/trackers/unique-id/telemetry"
              value={mqttTopic}
              onChange={(e) => setMqttTopic(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Initial Status</label>
            <select
              className="form-select"
              value={status}
              onChange={(e) => setStatus(e.target.value as TrackerStatus)}
            >
              <option value="OFFLINE">OFFLINE</option>
              <option value="ONLINE">ONLINE</option>
            </select>
          </div>

          {isSuperAdmin && (
            <div className="form-group">
              <label className="form-label">Target Organization ID (UUID)</label>
              <input
                type="text"
                required
                className="form-input"
                placeholder="00000000-0000-0000-0000-000000000000"
                value={targetOrgId}
                onChange={(e) => setTargetOrgId(e.target.value)}
              />
            </div>
          )}
        </form>
      </Modal>

      {/* Edit Tracker Modal */}
      <Modal
        isOpen={!!editingTracker}
        onClose={() => setEditingTracker(null)}
        title="Edit Tracker Details"
        footer={
          <>
            <button onClick={() => setEditingTracker(null)} className="btn btn-secondary">
              Cancel
            </button>
            <button onClick={handleEditSubmit} disabled={isSubmitting} className="btn btn-primary">
              {isSubmitting ? 'Saving...' : 'Save Changes'}
            </button>
          </>
        }
      >
        <form onSubmit={handleEditSubmit}>
          {formError && (
            <div style={{ padding: '10px', borderRadius: '6px', backgroundColor: 'var(--danger-bg)', border: '1px solid var(--danger-border)', color: 'var(--danger)', marginBottom: '16px', fontSize: '13px' }}>
              {formError}
            </div>
          )}
          <div className="form-group">
            <label className="form-label">Tracker Name</label>
            <input
              type="text"
              required
              className="form-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label">MQTT Telemetry Topic</label>
            <input
              type="text"
              required
              className="form-input"
              value={mqttTopic}
              onChange={(e) => setMqttTopic(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Status</label>
            <select
              className="form-select"
              value={status}
              onChange={(e) => setStatus(e.target.value as TrackerStatus)}
            >
              <option value="OFFLINE">OFFLINE</option>
              <option value="ONLINE">ONLINE</option>
            </select>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={!!deletingTracker}
        onClose={() => setDeletingTracker(null)}
        title="Confirm Tracker Deletion"
        footer={
          <>
            <button onClick={() => setDeletingTracker(null)} className="btn btn-secondary">
              Cancel
            </button>
            <button onClick={handleDelete} disabled={isSubmitting} className="btn btn-danger">
              {isSubmitting ? 'Deleting...' : 'Delete Tracker'}
            </button>
          </>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {deleteError ? (
            <div style={{ padding: '12px', borderRadius: '8px', backgroundColor: 'var(--danger-bg)', border: '1px solid var(--danger-border)', color: 'var(--danger)', fontSize: '13px' }}>
              <div style={{ fontWeight: 600, marginBottom: '4px' }}>Cannot Delete Tracker</div>
              {deleteError}
            </div>
          ) : (
            <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
              <AlertTriangle size={24} color="var(--warning)" style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>
                <p style={{ color: 'var(--text-main)', fontSize: '14px', fontWeight: 600 }}>
                  Are you sure you want to delete {deletingTracker?.name}?
                </p>
                <p style={{ color: 'var(--text-muted)', fontSize: '13px', marginTop: '4px' }}>
                  If this tracker has active shipments or telemetry records in PostgreSQL, the deletion will be rejected by database constraints.
                </p>
              </div>
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
};
