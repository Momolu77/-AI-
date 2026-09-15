import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, theme } from 'antd';
import SessionPage from './pages/SessionPage';
import HomePage from './pages/HomePage';

function App() {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#38BDF8',
          colorSuccess: '#6EE7B7',
          colorWarning: '#E9A568',
          colorError: '#F87171',
          colorBgBase: '#0A0D12',
          colorBgContainer: '#0F131C',
          colorBorder: '#1E2636',
          colorText: '#E5E7EB',
          colorTextSecondary: '#9CA3AF',
          borderRadius: 8,
          fontSize: 14,
        },
      }}
    >
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/session/:sessionId" element={<SessionPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
}

export default App;
