import React from 'react';
import { AuthProvider } from './context/AuthContext';
import { AppRouter } from './router/AppRouter';

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <AppRouter />
    </AuthProvider>
  );
};

export default App;
