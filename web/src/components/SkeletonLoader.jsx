import React from 'react';

export const SkeletonLoader = () => {
  return (
    <div className="glass-panel pulse-active" style={{ padding: '24px', marginBottom: '24px', borderRadius: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
        <div style={{ width: '24px', height: '24px', borderRadius: '50%', background: 'var(--border-subtle)', animation: 'pulse 1.5s infinite' }} />
        <div style={{ width: '60%', height: '16px', borderRadius: '4px', background: 'var(--border-subtle)', animation: 'pulse 1.5s infinite' }} />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <div style={{ width: '100%', height: '12px', borderRadius: '4px', background: 'var(--border-subtle)', animation: 'pulse 1.5s infinite' }} />
        <div style={{ width: '85%', height: '12px', borderRadius: '4px', background: 'var(--border-subtle)', animation: 'pulse 1.5s infinite' }} />
        <div style={{ width: '70%', height: '12px', borderRadius: '4px', background: 'var(--border-subtle)', animation: 'pulse 1.5s infinite' }} />
      </div>
    </div>
  );
};

export default SkeletonLoader;
