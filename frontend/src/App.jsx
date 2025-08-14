import { useEffect, useMemo, useState } from "react";
import { api, API_BASE_EFFECTIVE } from "./api";
import { Section } from "./components/Section";
import { PlayerRow } from "./components/PlayerRow";
import { PlayerTable } from "./components/PlayerTable";
import { POSITIONS } from "./lib/constants";

export default function App() {
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState(null);
  const [teams, setTeams] = useState([]);
  const [picks, setPicks] = useState([]);
  const [suggestTop, setSuggestTop] = useState([]);
  const [suggestNext, setSuggestNext] = useState([]);
  const [positionFilter, setPositionFilter] = useState("");
  const [playersTable, setPlayersTable] = useState([]);
  const [season] = useState(2025);

  // Admin import helpers
  const [ecrCsvPath, setEcrCsvPath] = useState("");
  const [adpCsvPath, setAdpCsvPath] = useState("");
  const [ecrHtmlUrl, setEcrHtmlUrl] = useState(
    "https://www.fantasypros.com/nfl/rankings/consensus-cheatsheets.php"
  );

  const [makePickForm, setMakePickForm] = useState({
    round_no: 1,
    overall_no: 1,
    team_slot_id: 1,
    player_id: "",
  });

  const reloadAll = async () => {
    setLoading(true);
    try {
      const [h, t, pk, sug] = await Promise.all([
        api.health(),
        api.teamsList(),
        api.picksList(),
        api.suggestions(positionFilter || null),
      ]);
      setHealth(h);
      setTeams(t);
      setPicks(pk);
      setSuggestTop(sug.top || []);
      setSuggestNext(sug.next || []);
      await loadPlayersTable();
    } catch (e) {
      console.error(e);
      alert("Error: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  const loadPlayersTable = async () => {
    try {
      const rows = await api.playersEnriched(season, positionFilter || "");
      setPlayersTable(rows);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    reloadAll(); // initial load
    // eslint-disable-next-line
  }, []);

  useEffect(() => {
    // when position changes, refresh suggestions and enriched table
    (async () => {
      try {
        const sug = await api.suggestions(positionFilter || null);
        setSuggestTop(sug.top || []);
        setSuggestNext(sug.next || []);
        await loadPlayersTable();
      } catch (e) {
        console.error(e);
      }
    })();
  }, [positionFilter]);

  const nextOverall = useMemo(
    () => (picks.length ? Math.max(...picks.map((p) => p.overall_no)) + 1 : 1),
    [picks]
  );

  const initTeams = async () => {
    await api.teamsInit();
    await reloadAll();
  };

  const onPick = async (player) => {
    const payload = {
      round_no: makePickForm.round_no,
      overall_no: makePickForm.overall_no || nextOverall,
      team_slot_id: makePickForm.team_slot_id,
      player_id: player?.player_id || makePickForm.player_id,
    };
    try {
      await api.makePick(payload);
      setMakePickForm((f) => ({ ...f, overall_no: payload.overall_no + 1 }));
      await reloadAll();
    } catch (e) {
      alert("Pick failed: " + e.message);
    }
  };

  const undo = async (pickId) => {
    await api.undoPick(pickId);
    await reloadAll();
  };

  const onTier = async (row, tierVal) => {
    await api.setTier(row.player_id, tierVal);
    await loadPlayersTable();
  };

  const onNote = async (row, text) => {
    await api.addNote(row.player_id, text, null);
    alert("Note added.");
  };

  // Admin import buttons
  const runImport = async (fn, label) => {
    try {
      await fn();
      await reloadAll();
      alert(`${label}: ok`);
    } catch (e) {
      alert(`${label}: ${e.message}`);
    }
  };

  return (
    <div
      style={{
        padding: 16,
        fontFamily: "system-ui, Arial",
        color: "#ddd",
        background: "#0e0e10",
        minHeight: "100vh",
      }}
    >
      <h2>Draft Room</h2>
      <div style={{ marginBottom: 12, opacity: 0.85 }}>
        API: <code>{API_BASE_EFFECTIVE || "(proxy /api)"}</code>
        &nbsp;|&nbsp; Health: {health ? "OK" : "…"}
        &nbsp;|&nbsp;
        <button onClick={reloadAll} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Section title="Setup">
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <button onClick={initTeams}>Init 12 Teams</button>
            <button
              onClick={() =>
                runImport(() => api.importSleeperPlayers(season), "Sleeper Players")
              }
            >
              Import Sleeper Players
            </button>
            <button
              onClick={() =>
                runImport(() => api.importInjuriesCBS(season), "CBS Injuries")
              }
            >
              Import CBS Injuries
            </button>
            <button
              onClick={async () => {
                await api.importDemo(); // still handy for quick testing
                await reloadAll();
              }}
            >
              Seed Demo Players
            </button>
            <span style={{ opacity: 0.75 }}>
              Teams: {teams.length} | Picks: {picks.length}
            </span>
          </div>

          <div style={{ marginTop: 8 }}>
            <label>Position filter:&nbsp;</label>
            <select
              value={positionFilter}
              onChange={(e) => setPositionFilter(e.target.value)}
            >
              <option value="">All</option>
              {POSITIONS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>

          <div style={{ marginTop: 12, textAlign: "left" }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>FantasyPros Imports (optional)</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 8, marginBottom: 8 }}>
              <input
                placeholder="Path to FantasyPros ECR CSV (on server)"
                value={ecrCsvPath}
                onChange={(e) => setEcrCsvPath(e.target.value)}
              />
              <button
                onClick={() =>
                  runImport(
                    () => api.importFPECRCsv(season, ecrCsvPath),
                    "FP ECR CSV"
                  )
                }
              >
                Import ECR CSV
              </button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 8, marginBottom: 8 }}>
              <input
                placeholder="FantasyPros ECR overall URL (HTML scrape fallback)"
                value={ecrHtmlUrl}
                onChange={(e) => setEcrHtmlUrl(e.target.value)}
              />
              <button
                onClick={() =>
                  runImport(() => api.importFPECRHtml(season, ecrHtmlUrl), "FP ECR HTML")
                }
              >
                Scrape ECR HTML
              </button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 8 }}>
              <input
                placeholder="Path to FantasyPros ADP CSV (on server)"
                value={adpCsvPath}
                onChange={(e) => setAdpCsvPath(e.target.value)}
              />
              <button
                onClick={() =>
                  runImport(
                    () => api.importFPADPCsv(season, adpCsvPath, "fp_composite"),
                    "FP ADP CSV"
                  )
                }
              >
                Import ADP CSV
              </button>
            </div>
          </div>
        </Section>

        <Section title="Make Pick (manual form)">
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: 8,
            }}
          >
            <div>
              <div>Round</div>
              <input
                type="number"
                value={makePickForm.round_no}
                onChange={(e) =>
                  setMakePickForm((f) => ({
                    ...f,
                    round_no: Number(e.target.value),
                  }))
                }
              />
            </div>
            <div>
              <div>Overall</div>
              <input
                type="number"
                value={makePickForm.overall_no || nextOverall}
                onChange={(e) =>
                  setMakePickForm((f) => ({
                    ...f,
                    overall_no: Number(e.target.value),
                  }))
                }
              />
            </div>
            <div>
              <div>Team Slot</div>
              <input
                type="number"
                value={makePickForm.team_slot_id}
                onChange={(e) =>
                  setMakePickForm((f) => ({
                    ...f,
                    team_slot_id: Number(e.target.value),
                  }))
                }
              />
            </div>
            <div>
              <div>Player ID</div>
              <input
                value={makePickForm.player_id}
                onChange={(e) =>
                  setMakePickForm((f) => ({
                    ...f,
                    player_id: e.target.value,
                  }))
                }
              />
            </div>
          </div>
          <div style={{ marginTop: 8 }}>
            <button onClick={() => onPick(null)}>Make Pick From Form</button>
          </div>
        </Section>

        <Section title="Suggestions — Top 3">
          {suggestTop.length === 0 ? (
            <div>No suggestions</div>
          ) : (
            suggestTop.map((p) => (
              <PlayerRow key={p.player_id} p={p} onPick={onPick} />
            ))
          )}
        </Section>

        <Section title="Next 10">
          {suggestNext.length === 0 ? (
            <div>—</div>
          ) : (
            suggestNext.map((p) => (
              <PlayerRow key={p.player_id} p={p} onPick={onPick} />
            ))
          )}
        </Section>

        <Section title="Players (Rank/Tier/ADP/Injuries)">
          <PlayerTable
            rows={playersTable}
            onPick={onPick}
            onTier={onTier}
            onNote={onNote}
          />
        </Section>

        <Section title="Picks">
          {picks.length === 0 ? (
            <div>No picks yet</div>
          ) : (
            picks.map((pk) => (
              <div
                key={pk.pick_id}
                style={{
                  display: "flex",
                  gap: 8,
                  alignItems: "center",
                  padding: "6px 0",
                  borderBottom: "1px solid #222",
                }}
              >
                <div style={{ width: 80 }}>#{pk.overall_no}</div>
                <div style={{ width: 60 }}>Rnd {pk.round_no}</div>
                <div style={{ width: 80 }}>Team {pk.team_slot_id}</div>
                <div style={{ width: 240 }}>{pk.player_id}</div>
                <div style={{ flex: 1 }} />
                <button onClick={() => undo(pk.pick_id)}>Undo</button>
              </div>
            ))
          )}
        </Section>
      </div>
    </div>
  );
}
