import { useEffect, useState } from "react";
import { api, API_BASE_EFFECTIVE } from "./api";
import { Section } from "./components/Section";
import { PlayerTable } from "./components/PlayerTable";
import { POSITIONS } from "./lib/constants";

const TEAMS = 12;

export default function App() {
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false); // spinner for runAll
  const [debug, setDebug] = useState([]);  // debug console lines
  const [teams, setTeams] = useState([]);
  const [picks, setPicks] = useState([]);
  const [position, setPosition] = useState("");
  const [q, setQ] = useState("");
  const [players, setPlayers] = useState([]);
  const [season, setSeason] = useState(new Date().getFullYear());

  const overallNext = picks.length + 1;
  const roundNext = Math.ceil(overallNext / TEAMS);

  async function boot() {
    setLoading(true);
    try {
      await api.teams.init();
      const [t, p] = await Promise.all([api.teams.list(), api.picks.list()]);
      setTeams(t);
      setPicks(p);
      await loadPlayers({ season, position, q });
    } finally {
      setLoading(false);
    }
  }

  async function loadPlayers({ season, position, q }) {
    const rows = await api.meta.playersEnriched({ season, position, q, limit: 500 });
    setPlayers(rows);
  }

  useEffect(() => {
    boot();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function makePick(player_id) {
    const payload = {
      player_id,
      team_slot_id: 1, // your team for now
      overall_no: overallNext,
      round_no: roundNext,
    };
    const pk = await api.picks.create(payload);
    setPicks((prev) => [...prev, pk]);
  }

  async function undoPick(pick_id) {
    await api.picks.delete(pick_id);
    setPicks((prev) => prev.filter((p) => p.pick_id !== pick_id));
  }

  async function runFullUpdate() {
    setBusy(true);
    setDebug((d) => [
      ...d,
      `Starting full data update for season ${season}...`,
    ]);
    try {
      const res = await api.admin.runAll(season);
      const lines = [];
      for (const step of res.logs || []) {
        lines.push(
          `STEP: ${step.step} | ok=${step.ok} code=${step.code ?? "n/a"}`
        );
        if (step.cmd) lines.push(`CMD: ${Array.isArray(step.cmd) ? step.cmd.join(" ") : step.cmd}`);
        if (step.stdout) lines.push(`STDOUT:\n${step.stdout}`);
        if (step.stderr) lines.push(`STDERR:\n${step.stderr}`);
      }
      setDebug((d) => [...d, ...lines]);
      // Reload players after update
      await loadPlayers({ season, position, q });
    } catch (e) {
      setDebug((d) => [...d, `ERROR: ${String(e)}`]);
    } finally {
      setBusy(false);
    }
  }

  const headerStyle = { display: "flex", gap: 12, alignItems: "center", marginBottom: 12 };

  return (
    <div style={{ padding: 16, color: "#eaeaea" }}>
      <div style={headerStyle}>
        <h2 style={{ margin: 0 }}>Draft Assistant</h2>
        <span style={{ opacity: 0.7 }}>API: {API_BASE_EFFECTIVE || "(proxy /api)"} </span>
        <div style={{ flex: 1 }} />
        <label>
          Season:&nbsp;
          <input
            type="number"
            value={season}
            onChange={(e) => setSeason(parseInt(e.target.value || new Date().getFullYear(), 10))}
            style={{ width: 90 }}
          />
        </label>
        <select value={position} onChange={(e) => setPosition(e.target.value)}>
          <option value="">All</option>
          {POSITIONS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <input
          placeholder="Search name/team..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") loadPlayers({ season, position, q });
          }}
          style={{ width: 220 }}
        />
        <button onClick={() => loadPlayers({ season, position, q })}>Refresh</button>
        <button onClick={runFullUpdate} disabled={busy} style={{ background: "#2b7", opacity: busy ? 0.7 : 1 }}>
          {busy ? "Updating…" : "Full Data Update"}
        </button>
      </div>

      {busy && (
        <div style={{ marginBottom: 12, padding: 8, background: "#222", border: "1px solid #333" }}>
          <span className="spinner" style={{ marginRight: 8 }}>⏳</span>
          Running scrapers and imports… please wait.
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>
        <Section title="Players">
          <PlayerTable
            rows={players}
            onPick={makePick}
            onTier={(player_id, tier) =>
              fetch(`/api/edits/tier/${encodeURIComponent(player_id)}?season=${season}&tier=${tier ?? ""}`, {
                method: "POST",
              }).then(() => loadPlayers({ season, position, q }))
            }
            onNote={(player_id, text) =>
              fetch(`/api/edits/notes?player_id=${encodeURIComponent(player_id)}&text=${encodeURIComponent(text)}`, {
                method: "POST",
              })
            }
          />
        </Section>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Section title="Your Next Pick">
            <div>Overall #{overallNext} (Round {roundNext})</div>
          </Section>

          <Section title="Debug Console">
            <div
              style={{
                background: "#0f0f0f",
                border: "1px solid #222",
                borderRadius: 8,
                padding: 8,
                height: 320,
                overflow: "auto",
                whiteSpace: "pre-wrap",
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
                fontSize: 12,
              }}
            >
              {debug.length ? debug.join("\n\n") : "No logs yet."}
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}
