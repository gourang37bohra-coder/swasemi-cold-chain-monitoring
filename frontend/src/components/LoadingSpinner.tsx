import React from 'react';

export const LoadingSpinner: React.FC<{ size?: number; label?: string }> = ({ size = 28, label }) => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '36px',
        gap: '12px',
      }}
    >
      <div
        style={{
          width: `${size}px`,
          height: `${size}px`,
          border: '3px solid rgba(56, 189, 248, 0.2)',
          borderTopColor: '#38bdf8',
          borderRadius: '50%',
          animation: 'spin 0.8s linear infinite',
        }}
      />
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
      {label && <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>{label}</p>}
    </div>
  );
};
