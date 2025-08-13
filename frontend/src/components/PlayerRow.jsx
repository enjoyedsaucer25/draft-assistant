export function PlayerRow({ p, onPick }) {
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", padding: "6px 0", borderBottom: "1px solid #222" }}>
      <div style={{ width: 220 }}>{p.clean_name}</div>
      <div style={{ width: 50 }}>{p.position}</div>
      <div style={{ width: 60 }}>{p.team ?? "-"}</div>
      <div style={{ flex: 1 }} />
      {onPick && <button onClick={() => onPick(p)}>Pick</button>}
    </div>
  );
}
