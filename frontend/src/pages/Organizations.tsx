import React, { useEffect, useState } from 'react';
import { Plus, Building2, Edit2, Users, Calendar, AlertTriangle, Search } from 'lucide-react';
import { adminApi } from '../api/client';
import type { Organization, OrganizationCreatePayload, OrganizationUpdatePayload } from '../types';
import { Card } from '../components/Card';
import { Modal } from '../components/Modal';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { EmptyState } from '../components/EmptyState';

export const Organizations: React.FC = () => {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal states
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingOrg, setEditingOrg] = useState<Organization | null>(null);
  const [orgName, setOrgName] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const fetchOrganizations = async (targetPage = page) => {
    try {
      setIsLoading(true);
      setError(null);
      const res = await adminApi.organizations.list({ page: targetPage, page_size: pageSize });
      setOrganizations(res.items);
      setTotal(res.total);
      setPage(res.page);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch organizations.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchOrganizations(page);
  }, [page]);

  const handleOpenCreate = () => {
    setOrgName('');
    setFormError(null);
    setIsCreateOpen(true);
  };

  const handleOpenEdit = (org: Organization) => {
    setEditingOrg(org);
    setOrgName(org.name);
    setFormError(null);
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!orgName.trim()) {
      setFormError('Organization name is required.');
      return;
    }

    try {
      setIsSubmitting(true);
      setFormError(null);
      const payload: OrganizationCreatePayload = { name: orgName.trim() };
      await adminApi.organizations.create(payload);
      setIsCreateOpen(false);
      setSuccessMessage('Organization created successfully.');
      setTimeout(() => setSuccessMessage(null), 4000);
      fetchOrganizations(1);
    } catch (err: any) {
      setFormError(err?.response?.data?.detail || 'Failed to create organization.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingOrg || !orgName.trim()) {
      setFormError('Organization name is required.');
      return;
    }

    try {
      setIsSubmitting(true);
      setFormError(null);
      const payload: OrganizationUpdatePayload = { name: orgName.trim() };
      await adminApi.organizations.update(editingOrg.id, payload);
      setEditingOrg(null);
      setSuccessMessage('Organization updated successfully.');
      setTimeout(() => setSuccessMessage(null), 4000);
      fetchOrganizations(page);
    } catch (err: any) {
      setFormError(err?.response?.data?.detail || 'Failed to update organization.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  const [searchTerm, setSearchTerm] = useState('');

  const filteredOrganizations = organizations.filter((org) => {
    if (!searchTerm.trim()) return true;
    const term = searchTerm.toLowerCase();
    return org.name.toLowerCase().includes(term) || org.id.toLowerCase().includes(term);
  });

  return (
    <div>
      <div className="page-header" style={{ marginBottom: '20px' }}>
        <div>
          <h1 className="page-title">Tenant Organizations</h1>
          <p className="page-subtitle">
            Manage multi-tenant client organizations and view tenant-specific metrics.
          </p>
        </div>
        <button className="btn btn-primary" onClick={handleOpenCreate}>
          <Plus size={16} />
          <span>Create Organization</span>
        </button>
      </div>

      {successMessage && (
        <div style={{ padding: '12px 16px', marginBottom: '16px', backgroundColor: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: '6px', color: 'var(--success)', fontSize: '13.5px' }}>
          {successMessage}
        </div>
      )}

      {error && (
        <div style={{ padding: '12px 16px', marginBottom: '16px', backgroundColor: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: '6px', color: 'var(--danger)', fontSize: '13.5px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <AlertTriangle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* Professional Search Toolbar */}
      <div
        className="card"
        style={{
          padding: '14px 18px',
          marginBottom: '20px',
          display: 'flex',
          flexWrap: 'wrap',
          gap: '14px',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ position: 'relative', width: '100%', maxWidth: '420px' }}>
          <input
            type="text"
            className="form-input"
            placeholder="Search organizations by name or UUID..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{ paddingLeft: '36px', height: '38px', fontSize: '13.5px' }}
          />
          <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            Total: <strong>{filteredOrganizations.length}</strong> organization(s)
          </span>
          {searchTerm && (
            <button
              type="button"
              className="btn btn-secondary"
              style={{ height: '36px', fontSize: '12px', padding: '0 12px' }}
              onClick={() => setSearchTerm('')}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      <Card>
        {isLoading ? (
          <div style={{ padding: '48px 0' }}>
            <LoadingSpinner label="Loading organizations..." />
          </div>
        ) : filteredOrganizations.length === 0 ? (
          <EmptyState
            message={searchTerm ? 'No matching organizations' : 'No organizations registered'}
            description={searchTerm ? `No organizations matched "${searchTerm}". Try another search query.` : 'Create your first client tenant organization to begin provisioning users and trackers.'}
            action={
              searchTerm ? (
                <button className="btn btn-secondary" onClick={() => setSearchTerm('')} style={{ fontSize: '13px' }}>
                  Clear Search
                </button>
              ) : (
                <button className="btn btn-primary" onClick={handleOpenCreate}>
                  <Plus size={16} />
                  <span>Create Organization</span>
                </button>
              )
            }
          />
        ) : (
          <>
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Organization Name</th>
                    <th>Organization UUID</th>
                    <th>Users Enrolled</th>
                    <th>Created At</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredOrganizations.map((org) => (
                    <tr key={org.id}>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600 }}>
                          <Building2 size={16} color="var(--primary)" />
                          <span style={{ color: 'var(--text-main)' }}>{org.name}</span>
                        </div>
                      </td>
                      <td>
                        <code style={{ fontSize: '12px', color: 'var(--text-main)', backgroundColor: 'var(--bg-main)', border: '1px solid var(--border)', padding: '2px 6px', borderRadius: '4px' }}>
                          {org.id}
                        </code>
                      </td>
                      <td>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', fontSize: '13px', color: 'var(--text-secondary)' }}>
                          <Users size={14} color="var(--text-muted)" />
                          <strong>{org.user_count ?? 0}</strong>
                        </span>
                      </td>
                      <td>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', fontSize: '12px', color: 'var(--text-muted)' }}>
                          <Calendar size={13} />
                          {new Date(org.created_at).toLocaleDateString()}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '5px 10px', fontSize: '12px' }}
                          onClick={() => handleOpenEdit(org)}
                          title="Edit Organization Name"
                        >
                          <Edit2 size={13} />
                          <span>Rename</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px', paddingTop: '16px', borderTop: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                  Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total} organizations
                </span>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    className="btn btn-secondary"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    Previous
                  </button>
                  <button
                    className="btn btn-secondary"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </Card>

      {/* Create Organization Modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Create Tenant Organization"
      >
        <form onSubmit={handleCreateSubmit}>
          {formError && (
            <div style={{ padding: '8px 12px', marginBottom: '12px', backgroundColor: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: '6px', color: 'var(--danger)', fontSize: '13px' }}>
              {formError}
            </div>
          )}

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--text-secondary)' }}>
              Organization Name *
            </label>
            <input
              type="text"
              className="input"
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              placeholder="e.g., Pfizer Global Cold-Chain, Apex Pharma"
              required
              autoFocus
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '20px' }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setIsCreateOpen(false)}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Creating...' : 'Create Organization'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Edit Organization Modal */}
      <Modal
        isOpen={!!editingOrg}
        onClose={() => setEditingOrg(null)}
        title="Rename Organization"
      >
        <form onSubmit={handleEditSubmit}>
          {formError && (
            <div style={{ padding: '8px 12px', marginBottom: '12px', backgroundColor: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: '6px', color: 'var(--danger)', fontSize: '13px' }}>
              {formError}
            </div>
          )}

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--text-secondary)' }}>
              Organization Name *
            </label>
            <input
              type="text"
              className="input"
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              placeholder="Organization Name"
              required
              autoFocus
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '20px' }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setEditingOrg(null)}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
