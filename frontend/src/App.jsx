import { useEffect, useMemo, useState } from "react";
import { api, API_BASE_EFFECTIVE } from "./api";
import { Section } from "./components/Section";
import { PlayerRow } from "./components/PlayerRow";
import { POSITIONS } from "./lib/constants";

export default function App() {
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState(null);
  const [teams, setTeams] = useState([]);
  const [picks, setPicks] = useState([]);
  const [suggestTop, setSuggestTop] = useState([]);
  const [suggestNext, setSuggestNext] = useState([]);
  const [positionFilter, setPositionFilter] = useState("");
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
    } catch (e) {
      console.error(e);
      alert("Error: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reloadAll(); // initial load
    // eslint-disable-next-line
  }, []);

  useEffect(() => {
    // refresh suggestions when position changes
    (async () => {
      try {
        const sug = await api.suggestions(positionFilter || null);
        setSuggestTop(sug.top || []);
        setSuggestNext(sug.next || []);
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
      <h2>Draft Room (Minimal)</h2>
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
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button onClick={initTeams}>Init 12 Teams</button>
            <button
              onClick={async () => {
                await api.importDemo();
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
