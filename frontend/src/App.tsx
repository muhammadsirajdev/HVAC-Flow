import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { getHealth } from "./api";
import { FanMark } from "./components/Icon";
import { usePoll } from "./lib/hooks";
import Office from "./pages/Office";
import TryIt from "./pages/TryIt";

export default function App() {
  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <TopBar />
      <main id="main">
        <Routes>
          <Route path="/" element={<TryIt />} />
          <Route path="/office" element={<Office />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}

function TopBar() {
  const health = usePoll(getHealth, 20000);
  const state = health.error ? "down" : health.data?.status === "ok" ? "up" : health.data ? "degraded" : "checking";
  const label = {
    up: "Connected",
    degraded: "Database unreachable",
    down: "API offline",
    checking: "Connecting",
  }[state];

  return (
    <header className="topbar">
      <div className="topbar__inner">
        <NavLink to="/" className="brand" aria-label="MD Cold Services, home">
          <FanMark size={30} />
          <span className="brand__name">
            MD Cold <span className="brand__sub">Services</span>
          </span>
        </NavLink>
        <nav className="nav" aria-label="Main">
          <NavLink to="/" end className="nav__link">Try it</NavLink>
          <NavLink to="/office" className="nav__link">Office</NavLink>
        </nav>
        <span className={`conn conn--${state}`} title={health.error ?? health.data?.database ?? ""}>
          <span className="conn__dot" aria-hidden="true" />
          <span className="conn__label">{label}</span>
        </span>
      </div>
    </header>
  );
}
