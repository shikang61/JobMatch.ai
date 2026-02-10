import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useAuthStore } from "./store/authStore";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import Dashboard from "./pages/Dashboard";
import JobMatchDetails from "./pages/JobMatchDetails";
import InterviewPrep from "./pages/InterviewPrep";
import InterviewPractice from "./pages/InterviewPractice";
import ProgressDashboard from "./pages/ProgressDashboard";
import PeerComparison from "./pages/PeerComparison";
import AccountPage from "./pages/AccountPage";
import Layout from "./components/Layout";

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated());
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/"
          element={
            <PrivateRoute>
              <Layout />
            </PrivateRoute>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="job/:jobId" element={<JobMatchDetails />} />
          <Route path="match/:matchId" element={<JobMatchDetails />} />
          <Route path="prep/:prepId" element={<InterviewPrep />} />
          <Route path="practice/session/:sessionId" element={<InterviewPractice />} />
          <Route path="progress" element={<ProgressDashboard />} />
          <Route path="peers" element={<PeerComparison />} />
          <Route path="account" element={<AccountPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
