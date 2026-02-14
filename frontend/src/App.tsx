import { Routes, Route, Navigate } from "react-router-dom";
import Home from "./pages/Home";
import Dashboard from "./pages/Dashboard";
import RepoView from "./pages/RepoView";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/repo/:owner/:repo" element={<RepoView />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
