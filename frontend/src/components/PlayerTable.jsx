import { useState } from "react";

export function PlayerTable({ rows, onPick, onTier, onNote }) {
  if (!rows?.length) return <div>No players loaded.</div>;

  return (
    <div style={{ border: "1px solid #333", borderRadius: 8, overflow: "hidden" }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "60px 220px 60px 60px 60px 80px 200px 120px 140px",
          gap: 8,
          padding: "8px 12px",
          background: "#151515",
          fontWeight: 600,
        }}
      >
        <div>ECR</div>
        <div>Name</div>
        <div>Pos</div>
        <div>Team</div>
        <div>Tier</div>
        <div>ADP</div>
        <div>Injury</div>
        <div>Tier Edit</div>
        <div>Notes</div>
      </div>

      {rows.map((r) => (
        <Row
          key={r.player_id}
          r={r}
          onPick={onPick}
          onTier={onTier}
          onNote={onNote}
        />
      ))}
    </div>
  );
}

function Row({ r, onPick, onTier, onNote }) {
  const [tierText, setTierText] = useState("");

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns:
          "60px 220px 60px 60px 60px 80px 200px 120px 140px",
        gap: 8,
        padding: "6px 12px",
        borderTop: "1px solid #222",
        alignItems: "center",
      }}
    >
      <div>{r.ecr ?? "—"}</div>

      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <span title={r.player_id}>{r.name}</span>
        <button onClick={() => onPick(r)} title="Pick">
          Pick
        </button>
      </div>

      <div>{r.pos}</div>
      <div>{r.team ?? "—"}</div>
      <div title={r.tier_source === "override" ? "Overridden" : "Core"}>
        {r.tier ?? "—"}
      </div>
      <div>{r.adp ?? "—"}</div>
      <div>
        {r.injury_status
          ? `${r.injury_status}${r.injury_body ? ` (${r.injury_body})` : ""}`
          : "—"}
      </div>

      <div>
        <input
          style={{ width: 60 }}
          placeholder="tier"
          value={tierText}
          onChange={(e) => setTierText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              const v = tierText.trim();
              onTier(r, v === "" ? null : Number(v));
              setTierText("");
            }
          }}
        />
      </div>

      <div>
        <button
          onClick={() => {
            const text = prompt(`Note for ${r.name}:`);
            if (text) onNote(r, text);
          }}
        >
          Add
        </button>
      </div>
    </div>
  );
}
