import { useState } from "react";

export function PlayerTable({ rows, onPick, onTier, onNote }) {
  const [tierInput, setTierInput] = useState({});
  const [noteInput, setNoteInput] = useState({});

  if (!rows?.length) return <div>No players loaded.</div>;

  return (
    <div style={{ border: "1px solid #333", borderRadius: 8, overflow: "hidden" }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "60px 220px 60px 60px 60px 80px 80px 200px 120px 140px",
          gap: 8,
          padding: "8px 12px",
          background: "#151515",
          fontWeight: 600,
        }}
      >
        <div>#</div>
        <div>Name</div>
        <div>Pos</div>
        <div>Team</div>
        <div>Tier</div>
        <div>ADP</div>
        <div>Proj</div>
        <div>Injury</div>
        <div>Tier Override</div>
        <div>Actions</div>
      </div>

      {rows.map((r, i) => (
        <div
          key={r.player_id}
          style={{
            display: "grid",
            gridTemplateColumns:
              "60px 220px 60px 60px 60px 80px 80px 200px 120px 140px",
            gap: 8,
            padding: "8px 12px",
            borderBottom: "1px solid #222",
            alignItems: "center",
          }}
        >
          <div>{i + 1}</div>
          <div>{r.name}</div>
          <div>{r.pos}</div>
          <div>{r.team ?? "—"}</div>
          <div title={r.tier_source === "override" ? "Overridden" : "Core"}>{r.tier ?? "—"}</div>
          <div>{r.adp ?? "—"}</div>
          <div>{r.proj_pts ?? "—"}</div>
          <div>
            {r.injury_status ? `${r.injury_status}${r.injury_body ? ` (${r.injury_body})` : ""}` : "—"}
          </div>

          <div>
            <input
              style={{ width: 60 }}
              type="number"
              placeholder="Tier"
              value={tierInput[r.player_id] ?? ""}
              onChange={(e) =>
                setTierInput((s) => ({ ...s, [r.player_id]: e.target.value }))
              }
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  const v = tierInput[r.player_id];
                  onTier(r.player_id, v === "" ? null : parseInt(v, 10));
                }
              }}
            />
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={() => onPick(r.player_id)}>Pick</button>
            <input
              placeholder="Note…"
              value={noteInput[r.player_id] ?? ""}
              onChange={(e) =>
                setNoteInput((s) => ({ ...s, [r.player_id]: e.target.value }))
              }
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  const t = noteInput[r.player_id];
                  if (t?.trim()) onNote(r.player_id, t.trim());
                  setNoteInput((s) => ({ ...s, [r.player_id]: "" }));
                }
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
