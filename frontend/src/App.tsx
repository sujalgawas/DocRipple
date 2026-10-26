import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { AppShell } from "./components/layout/AppShell";
import { RepositoriesPage } from "./pages/RepositoriesPage";
import { RepoDetailPage } from "./pages/RepoDetailPage";
import { AddRepositoryPage } from "./pages/AddRepositoryPage";
import { ActivityPage } from "./pages/ActivityPage";

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public Routes */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />

        {/* Authenticated Dashboard Routes */}
        <Route element={<AppShell />}>
          <Route path="/repositories" element={<RepositoriesPage />} />
          <Route path="/repositories/new" element={<AddRepositoryPage />} />
          <Route path="/repositories/:owner/:repo" element={<RepoDetailPage />} />
          <Route path="/activity" element={<ActivityPage />} />
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;
