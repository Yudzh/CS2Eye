import {
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import {
  AdminTeamsPage,
} from "./pages/AdminTeamsPage";

import {
  AdminTeamsImportPage,
} from "./pages/AdminTeamsImportPage";

import {
  AppShell,
} from "./components/AppShell";

import {
  CompareTeamsPage,
} from "./pages/CompareTeamsPage";

import {
  TeamDetailsPage,
} from "./pages/TeamDetailsPage";

import {
  TeamsPage,
} from "./pages/TeamsPage";


export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route
          element={<AdminTeamsImportPage />}
          path="/admin/teams/import"
        />

        <Route
          element={<AdminTeamsPage />}
          path="/admin/teams"
        />

        <Route
          element={
            <Navigate
              replace
              to="/teams"
            />
          }
          path="/"
        />

        <Route
          element={<TeamsPage />}
          path="/teams"
        />

        <Route
          element={<TeamDetailsPage />}
          path="/teams/:teamId"
        />

        <Route
          element={<CompareTeamsPage />}
          path="/compare"
        />

        <Route
          element={
            <Navigate
              replace
              to="/teams"
            />
          }
          path="*"
        />
      </Routes>
    </AppShell>
  );
}