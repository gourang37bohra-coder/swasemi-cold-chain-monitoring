import React from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Radio, Package, LogOut, Shield, Building2, Users } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export const AppLayout: React.FC = () => {
  const { user, logout, isSuperAdmin } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="app-container">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo">SC</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: '15px', color: '#fff', letterSpacing: '-0.01em' }}>
              SWASEMI
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Cold-Chain Monitor
            </div>
          </div>
        </div>

        <nav className="sidebar-nav">
          <NavLink
            to="/dashboard"
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <LayoutDashboard size={18} />
            <span>Dashboard</span>
          </NavLink>

          <NavLink
            to="/trackers"
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <Radio size={18} />
            <span>Trackers</span>
          </NavLink>

          <NavLink
            to="/shipments"
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <Package size={18} />
            <span>Shipments</span>
          </NavLink>

          {isSuperAdmin && (
            <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px solid rgba(220, 227, 234, 0.12)' }}>
              <div style={{ padding: '0 12px 8px 12px', fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Administration
              </div>
              <NavLink
                to="/organizations"
                className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
              >
                <Building2 size={18} />
                <span>Organizations</span>
              </NavLink>
              <NavLink
                to="/users"
                className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
              >
                <Users size={18} />
                <span>Users</span>
              </NavLink>
            </div>
          )}
        </nav>

        <div className="sidebar-footer">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-secondary)' }}>
              {isSuperAdmin ? <Shield size={14} color="#D99A22" /> : <Building2 size={14} color="#2F80C0" />}
              <span style={{ fontWeight: 600 }}>{user?.role}</span>
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={user?.email}>
              {user?.email}
            </div>
            {user?.organization_id && (
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={user.organization_id}>
                Org: {user.organization_id.slice(0, 8)}...
              </div>
            )}
          </div>
          <button
            onClick={handleLogout}
            className="sidebar-signout-btn"
          >
            <LogOut size={16} />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Main App Body */}
      <div className="main-content">
        <header className="topbar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '13px', fontWeight: 600 }}>
              {isSuperAdmin ? (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    color: '#9A680C',
                    backgroundColor: '#FEF7E8',
                    border: '1px solid #F7DC9F',
                    padding: '4px 10px',
                    borderRadius: '6px',
                  }}
                >
                  <Shield size={14} /> Platform Admin Mode (Cross-Tenant Scope)
                </span>
              ) : (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    color: '#2F80C0',
                    backgroundColor: '#EAF4FC',
                    border: '1px solid #BCD9F1',
                    padding: '4px 10px',
                    borderRadius: '6px',
                  }}
                >
                  <Building2 size={14} /> Organization Scoped Tenant
                </span>
              )}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              <span style={{ color: 'var(--text-muted)' }}>Logged in as: </span>
              <strong style={{ color: 'var(--text-main)' }}>{user?.email}</strong>
            </div>
          </div>
        </header>

        <main className="page-body">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
