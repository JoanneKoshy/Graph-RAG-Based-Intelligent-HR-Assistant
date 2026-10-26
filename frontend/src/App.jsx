// Layout: sidebar navigation + the current page. Chat history lives here so it survives page switches.
import { useState } from "react";
import AskPage from "./pages/AskPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import PeoplePage from "./pages/PeoplePage.jsx";
import GraphPage from "./pages/GraphPage.jsx";

const PAGES = [
  { id: "ask", label: "Ask the assistant", icon: "\u{1F4AC}" },
  { id: "dashboard", label: "Workforce dashboard", icon: "\u{1F4CA}" },
  { id: "people", label: "Employee profile", icon: "\u{1F464}" },
  { id: "graph", label: "Knowledge graph", icon: "\u{1F578}" },
];

export default function App() {
  const [page, setPage] = useState("ask");
  const [chat, setChat] = useState([]);
  const [pending, setPending] = useState(null);
  const [profileId, setProfileId] = useState(null);

  const askAbout = (question) => {
    setPending(question);
    setPage("ask");
  };
  const openProfile = (empId) => {
    setProfileId(empId);
    setPage("people");
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">N</div>
          <div>
            <div className="brand-name">Nexora HR Assistant</div>
            <div className="brand-sub">Graph RAG workforce decision support</div>
          </div>
        </div>
        <nav>
          {PAGES.map((p) => (
            <button key={p.id} className={"nav-item" + (page === p.id ? " active" : "")} onClick={() => setPage(p.id)}>
              <span className="nav-icon">{p.icon}</span>
              {p.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot muted small">
          CSD 415 &middot; Team 11 &middot; MITS Kochi
        </div>
      </aside>
      <main className="content">
        {page === "ask" && (
          <AskPage chat={chat} setChat={setChat} pending={pending} clearPending={() => setPending(null)} />
        )}
        {page === "dashboard" && <DashboardPage openProfile={openProfile} />}
        {page === "people" && <PeoplePage empId={profileId} setEmpId={setProfileId} askAbout={askAbout} />}
        {page === "graph" && <GraphPage />}
      </main>
    </div>
  );
}
