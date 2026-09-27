import React, { useEffect, useState } from 'react';
import { Plus, Edit2, Shield, Building2, Search, Filter, AlertTriangle } from 'lucide-react';
import { adminApi } from '../api/client';
import type { AdminUser, AdminUserCreatePayload, AdminUserUpdatePayload, Organization, UserRole } from '../types';
import { Card } from '../components/Card';
import { Modal } from '../components/Modal';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { EmptyState } from '../components/EmptyState';

export const Users: React.FC = () => {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [filterOrg, setFilterOrg] = useState('');
  const [filterRole, setFilterRole] = useState('');
  const [searchEmail, setSearchEmail] = useState('');

  // Create Modal states
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createEmail, setCreateEmail] = useState('');
  const [createPassword, setCreatePassword] = useState('');
  const [createRole, setCreateRole] = useState<UserRole>('USER');
  const [createOrgId, setCreateOrgId] = useState('');

  // Edit Modal states
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const [editRole, setEditRole] = useState<UserRole>('USER');
  const [editOrgId, setEditOrgId] = useState('');
  const [editNewPassword, setEditNewPassword] = useState('');

  // Form submission feedback
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Load organizations for dropdowns & lookup
  const loadOrganizations = async () => {
    try {
      const res = await adminApi.organizations.list({ page: 1, page_size: 100 });
      setOrganizations(res.items);
    } catch {
      // Non-blocking for page load
    }
  };

  const fetchUsers = async (targetPage = page) => {
    try {
      setIsLoading(true);
      setError(null);
      const params: {
        page: number;
        page_size: number;
        organization_id?: string;
        role?: string;
        email?: string;
      } = {
        page: targetPage,
        page_size: pageSize,
      };
      if (filterOrg) params.organization_id = filterOrg;
      if (filterRole) params.role = filterRole;
      if (searchEmail.trim()) params.email = searchEmail.trim();

      const res = await adminApi.users.list(params);
      setUsers(res.items);
      setTotal(res.total);
      setPage(res.page);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch users.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadOrganizations();
  }, []);

  useEffect(() => {
    fetchUsers(page);
  }, [page, filterOrg, filterRole]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchUsers(1);
  };

  const handleOpenCreate = () => {
    setCreateEmail('');
    setCreatePassword('');
    setCreateRole('USER');
    setCreateOrgId(organizations.length > 0 ? organizations[0].id : '');
    setFormError(null);
    setIsCreateOpen(true);
  };

  const handleOpenEdit = (user: AdminUser) => {
    setEditingUser(user);
    setEditRole(user.role);
    setEditOrgId(user.organization_id || (organizations.length > 0 ? organizations[0].id : ''));
    setEditNewPassword('');
    setFormError(null);
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createEmail.trim()) {
      setFormError('Email is required.');
      return;
    }
    if (createPassword.length < 8) {
      setFormError('Password must be at least 8 characters long.');
      return;
    }
    if (createRole === 'USER' && !createOrgId) {
      setFormError('Target organization is required for USER accounts.');
      return;
    }

    try {
      setIsSubmitting(true);
      setFormError(null);
      const payload: AdminUserCreatePayload = {
        email: createEmail.trim(),
        password: createPassword,
        role: createRole,
        organization_id: createRole === 'USER' ? createOrgId : null,
      };

      await adminApi.users.create(payload);
      setIsCreateOpen(false);
      setSuccessMessage(`User "${createEmail.trim()}" provisioned successfully.`);
      setTimeout(() => setSuccessMessage(null), 4000);
      fetchUsers(1);
    } catch (err: any) {
      setFormError(err?.response?.data?.detail || 'Failed to create user.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingUser) return;

    if (editRole === 'USER' && !editOrgId) {
      setFormError('Target organization is required for USER accounts.');
      return;
    }
    if (editNewPassword && editNewPassword.length < 8) {
      setFormError('New password must be at least 8 characters long.');
      return;
    }

    try {
      setIsSubmitting(true);
      setFormError(null);
      const payload: AdminUserUpdatePayload = {
        role: editRole,
        organization_id: editRole === 'USER' ? editOrgId : null,
        ...(editNewPassword ? { password: editNewPassword } : {}),
      };

      await adminApi.users.update(editingUser.id, payload);
      setEditingUser(null);
      setSuccessMessage(`User "${editingUser.email}" updated successfully.`);
      setTimeout(() => setSuccessMessage(null), 4000);
      fetchUsers(page);
    } catch (err: any) {
      setFormError(err?.response?.data?.detail || 'Failed to update user.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const orgNameMap = new Map(organizations.map((o) => [o.id, o.name]));
  const totalPages = Math.ceil(total / pageSize);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">User Accounts</h1>
          <p className="page-subtitle">
            Provision and manage tenant operator accounts and platform administrators (Invite-Only).
          </p>
        </div>
        <button className="btn btn-primary" onClick={handleOpenCreate}>
          <Plus size={16} />
          <span>Create User</span>
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

      {/* Professional Filter Toolbar */}
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
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: '8px', flex: '1 1 320px', maxWidth: '440px' }}>
          <div style={{ position: 'relative', width: '100%' }}>
            <input
              type="text"
              className="form-input"
              placeholder="Search user accounts by email..."
              value={searchEmail}
              onChange={(e) => setSearchEmail(e.target.value)}
              style={{ paddingLeft: '36px', height: '38px', fontSize: '13.5px' }}
            />
            <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          </div>
          <button type="submit" className="btn btn-secondary" style={{ height: '38px', padding: '0 16px' }}>
            Search
          </button>
        </form>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '12.5px', fontWeight: 600, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Filter size={14} color="var(--text-muted)" /> Filters:
          </span>

          <select
            className="form-select"
            value={filterRole}
            onChange={(e) => {
              setFilterRole(e.target.value);
              setPage(1);
            }}
            style={{ width: 'auto', minWidth: '130px', height: '38px', cursor: 'pointer' }}
          >
            <option value="">All Roles</option>
            <option value="USER">USER</option>
            <option value="SUPER_ADMIN">SUPER_ADMIN</option>
          </select>

          <select
            className="form-select"
            value={filterOrg}
            onChange={(e) => {
              setFilterOrg(e.target.value);
              setPage(1);
            }}
            style={{ width: 'auto', minWidth: '180px', height: '38px', cursor: 'pointer' }}
          >
            <option value="">All Organizations</option>
            {organizations.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name}
              </option>
            ))}
          </select>

          {(searchEmail || filterRole || filterOrg) && (
            <button
              type="button"
              className="btn btn-secondary"
              style={{ height: '38px', fontSize: '12.5px', padding: '0 12px' }}
              onClick={() => {
                setSearchEmail('');
                setFilterRole('');
                setFilterOrg('');
                setPage(1);
                fetchUsers(1);
              }}
            >
              Reset
            </button>
          )}
        </div>
      </div>

      <Card>
        {isLoading ? (
          <div style={{ padding: '48px 0' }}>
            <LoadingSpinner label="Loading user accounts..." />
          </div>
        ) : users.length === 0 ? (
          <EmptyState
            message="No users found"
            description="Provision a new user account with tenant organization assignment."
            action={
              <button className="btn btn-primary" onClick={handleOpenCreate}>
                <Plus size={16} />
                <span>Create User</span>
              </button>
            }
          />
        ) : (
          <>
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Email Address</th>
                    <th>Role</th>
                    <th>Assigned Organization</th>
                    <th>Created At</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => {
                    const orgName = u.organization_id ? orgNameMap.get(u.organization_id) || u.organization_id : 'Platform Wide';
                    return (
                      <tr key={u.id}>
                        <td>
                          <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>{u.email}</span>
                        </td>
                        <td>
                          {u.role === 'SUPER_ADMIN' ? (
                            <span
                              className="badge"
                              style={{
                                backgroundColor: 'var(--warning-bg)',
                                color: '#9A680C',
                                border: '1px solid var(--warning-border)',
                                padding: '3px 8px',
                              }}
                            >
                              <Shield size={12} style={{ marginRight: '4px' }} />
                              SUPER_ADMIN
                            </span>
                          ) : (
                            <span
                              className="badge"
                              style={{
                                backgroundColor: 'var(--primary-light)',
                                color: 'var(--primary)',
                                border: '1px solid var(--primary-border)',
                                padding: '3px 8px',
                              }}
                            >
                              <Building2 size={12} style={{ marginRight: '4px' }} />
                              USER
                            </span>
                          )}
                        </td>
                        <td>
                          <span style={{ fontSize: '13px', color: u.organization_id ? 'var(--text-main)' : 'var(--text-muted)' }}>
                            {orgName}
                          </span>
                        </td>
                        <td>
                          <span style={{ fontSize: '12.5px', color: 'var(--text-muted)' }}>
                            {new Date(u.created_at).toLocaleDateString()}
                          </span>
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          <button
                            className="btn btn-secondary"
                            style={{ padding: '5px 10px', fontSize: '12px' }}
                            onClick={() => handleOpenEdit(u)}
                            title="Edit User"
                          >
                            <Edit2 size={13} />
                            <span>Edit</span>
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px', paddingTop: '16px', borderTop: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                  Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total} users
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

      {/* Create User Modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Provision New User"
      >
        <form onSubmit={handleCreateSubmit}>
          {formError && (
            <div style={{ padding: '8px 12px', marginBottom: '12px', backgroundColor: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: '6px', color: 'var(--danger)', fontSize: '13px' }}>
              {formError}
            </div>
          )}

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--text-secondary)' }}>
              Email Address *
            </label>
            <input
              type="email"
              className="input"
              value={createEmail}
              onChange={(e) => setCreateEmail(e.target.value)}
              placeholder="operator@organization.com"
              required
              autoFocus
            />
          </div>

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--text-secondary)' }}>
              Initial Password * (min 8 characters)
            </label>
            <input
              type="password"
              className="input"
              value={createPassword}
              onChange={(e) => setCreatePassword(e.target.value)}
              placeholder="••••••••"
              minLength={8}
              required
            />
          </div>

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--text-secondary)' }}>
              Role *
            </label>
            <select
              className="input"
              value={createRole}
              onChange={(e) => setCreateRole(e.target.value as UserRole)}
            >
              <option value="USER">USER (Organization Operator)</option>
              <option value="SUPER_ADMIN">SUPER_ADMIN (Platform Administrator)</option>
            </select>
          </div>

          {createRole === 'USER' && (
            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--text-secondary)' }}>
                Target Organization *
              </label>
              <select
                className="input"
                value={createOrgId}
                onChange={(e) => setCreateOrgId(e.target.value)}
                required
              >
                {organizations.length === 0 ? (
                  <option value="">No organizations available (Create one first)</option>
                ) : (
                  organizations.map((org) => (
                    <option key={org.id} value={org.id}>
                      {org.name}
                    </option>
                  ))
                )}
              </select>
            </div>
          )}

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
              disabled={isSubmitting || (createRole === 'USER' && organizations.length === 0)}
            >
              {isSubmitting ? 'Provisioning...' : 'Provision User'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Edit User Modal */}
      <Modal
        isOpen={!!editingUser}
        onClose={() => setEditingUser(null)}
        title={`Edit User: ${editingUser?.email}`}
      >
        <form onSubmit={handleEditSubmit}>
          {formError && (
            <div style={{ padding: '8px 12px', marginBottom: '12px', backgroundColor: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: '6px', color: 'var(--danger)', fontSize: '13px' }}>
              {formError}
            </div>
          )}

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--text-secondary)' }}>
              Role *
            </label>
            <select
              className="input"
              value={editRole}
              onChange={(e) => setEditRole(e.target.value as UserRole)}
            >
              <option value="USER">USER (Organization Operator)</option>
              <option value="SUPER_ADMIN">SUPER_ADMIN (Platform Administrator)</option>
            </select>
          </div>

          {editRole === 'USER' && (
            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--text-secondary)' }}>
                Target Organization *
              </label>
              <select
                className="input"
                value={editOrgId}
                onChange={(e) => setEditOrgId(e.target.value)}
                required
              >
                {organizations.map((org) => (
                  <option key={org.id} value={org.id}>
                    {org.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--text-secondary)' }}>
              Set New Password (optional)
            </label>
            <input
              type="password"
              className="input"
              value={editNewPassword}
              onChange={(e) => setEditNewPassword(e.target.value)}
              placeholder="Leave blank to keep existing password"
              minLength={8}
            />
            <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px', display: 'block' }}>
              If specified, the password will be bcrypt hashed immediately by the backend.
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '20px' }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setEditingUser(null)}
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
