export function Section({ title, children }) {
  return (
    <div style={{ padding: 12, border: "1px solid #333", borderRadius: 8, marginBottom: 12 }}>
      <h3 style={{ marginTop: 0 }}>{title}</h3>
      {children}
    </div>
  );
}
