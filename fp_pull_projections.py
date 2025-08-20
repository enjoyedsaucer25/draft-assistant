import asyncio, argparse, csv, json, os, re, sqlite3, sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# deps:
#   pip install playwright
#   python -m playwright install chromium
from playwright.async_api import async_playwright

BASE_URL = "https://www.fantasypros.com/nfl/projections/{pos}.php?week={week}"

# --------------------------
# Helpers & normalizers
# --------------------------
def _extract_name_team(cell: str) -> Tuple[str, Optional[str]]:
    """
    Player cell may look like "Saquon Barkley PHI" or "Ja'Marr Chase (CIN) (10)".
    Return (name, team). (We ignore bye on purpose.)
    """
    s = (cell or "").strip()
    s = re.sub(r"\s*\(\d{1,2}\)\s*$", "", s).strip()   # strip trailing "(10)" if present
    m_paren = re.search(r"\(([A-Z]{2,3})\)\s*$", s)
    if m_paren:
        team = m_paren.group(1)
        name = re.sub(r"\s+\([A-Z]{2,3}\)\s*$", "", s).strip()
        return name, team
    m_space = re.search(r"\s+([A-Z]{2,3})\s*$", s)
    if m_space:
        team = m_space.group(1)
        name = re.sub(r"\s+[A-Z]{2,3}\s*$", "", s).strip()
        return name, team
    return s, None

def _to_float(x: str) -> Optional[float]:
    try:
        x = (x or "").replace(",", ".")
        m = re.search(r"-?\d+(?:\.\d+)?", x)
        return float(m.group(0)) if m else None
    except:
        return None

def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("%", " pct")
    s = re.sub(r"[()\[\]]", "", s)
    s = re.sub(r"[\/\-]", " ", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s

def _normalize_key(raw: str) -> str:
    """
    Map grouped headers to unique, friendly names.
    Important special-cases so rushing/receiving/passing columns never collide.
    """
    k = _slug(raw)

    # Standardize big groups first
    k = k.replace("rushing_", "rush_").replace("receiving_", "rec_").replace("passing_", "pass_")

    # FPts
    if k in {"fpts", "fantasy_points", "fantasy_points_ppr", "points", "pts", "proj_pts"}:
        return "proj_pts"

    # Player/Team/Pos
    if k in {"player", "player_name", "player_team", "player_team_bye"}:
        return "player"
    if k in {"tm", "team", "teams"}:
        return "team"
    if k == "pos":
        return "pos"

    # MISC
    if k == "misc_fl":
        return "fl"

    # Receiving special cases (keep "rec" for receptions, "tgt" for targets)
    if k == "rec_rec":
        return "rec"
    if k == "rec_tgt" or k == "rec_tgts" or k == "rec_targets":
        return "tgt"

    # Passing special cases
    if k in {"pass_cmp_pct", "pass_completion_pct"}:
        return "pass_cmp_pct"
    if k in {"pass_int", "pass_ints"}:
        return "pass_int"

    # Some tables use generic leaf headers with a nearby group-less FPts column; we already handled FPts.
    return k

def _numify_row(d: Dict[str, object]) -> Dict[str, object]:
    out: Dict[str, object] = {}
    for k, v in d.items():
        if k in ("player_name", "team", "pos"):
            out[k] = "" if v is None else str(v)
        elif k == "proj_pts":
            out[k] = None if v is None else _to_float(str(v))
        else:
            if isinstance(v, (int, float)):
                out[k] = float(v)
            else:
                out[k] = None if v is None else _to_float(str(v))
    return out

# --------------------------
# Build header grid (handles colspan/rowspan) via JS
# --------------------------
JS_GET_TABLE = """
() => {
  const table = Array.from(document.querySelectorAll('table')).find(t => t.querySelector('thead'));
  if (!table) return {headers: [], rows: []};
  const thead = table.querySelector('thead');
  const rows = Array.from(thead.querySelectorAll('tr'));

  // Build grid of header texts per final column (handles row/col spans)
  const grid = [];
  let maxCols = 0;
  // track remaining rowspans for each column index
  let spanDown = [];

  for (let r = 0; r < rows.length; r++) {
    const cells = Array.from(rows[r].children);
    let ci = 0;
    // skip through columns already occupied via rowspan
    function skipOccupied() {
      while (spanDown[ci] > 0) { spanDown[ci]--; ci++; }
    }
    skipOccupied();

    for (const cell of cells) {
      const colspan = parseInt(cell.getAttribute('colspan') || '1');
      const rowspan = parseInt(cell.getAttribute('rowspan') || '1');
      const text = (cell.innerText || '').trim();

      for (let k = 0; k < colspan; k++) {
        const col = ci + k;
        if (!grid[col]) grid[col] = Array(rows.length).fill("");
        grid[col][r] = text;
      }

      // mark the spanned columns as occupied downward
      for (let k = 0; k < colspan; k++) {
        spanDown[ci + k] = (rowspan > 1 ? rowspan - 1 : 0);
      }
      ci += colspan;
      skipOccupied();
    }
    if (ci > maxCols) maxCols = ci;
  }

  // Build header names: use nearest group above leaf; ignore Player/Rank/Bye groups
  const headers = [];
  for (let c = 0; c < maxCols; c++) {
    const path = (grid[c] || []).map(t => (t || '').trim()).filter(Boolean);
    const leaf = path[path.length - 1] || "";
    const groups = path.slice(0, -1).filter(g => !/^(player|rank|#|rk|bye)$/i.test(g));
    const group = groups.length ? groups[groups.length - 1] : "";
    let name = leaf;
    if (group) name = `${group} ${leaf}`;
    headers.push(name);
  }

  // Body rows
  const bodyRows = Array.from(table.querySelectorAll('tbody tr')).map(tr =>
    Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim())
  );

  return {headers, rows: bodyRows};
}
"""

def _rows_from_grouped_headers(headers: List[str], rows: List[List[str]], pos: str) -> List[Dict[str, object]]:
    # normalize and drop any rank/bye if they appear
    norm = [_normalize_key(h) for h in headers]
    drop = {"rank", "rk", "#", "bye", "proj_rank"}  # we don't want these in this scraper
    keep_idx = [i for i, h in enumerate(norm) if h not in drop]
    norm = [norm[i] for i in keep_idx]

    out: List[Dict[str, object]] = []
    for cells in rows:
        if not cells: 
            continue
        vals = [(cells[i] if i < len(cells) else "") for i in keep_idx]
        r: Dict[str, object] = {norm[i]: vals[i] for i in range(len(norm))}

        # Pull player/team from 'player' or keep separate 'team' if present
        player_cell = str(r.get("player", "") or "")
        name, team = _extract_name_team(player_cell)

        r["player_name"] = name
        r["team"] = team or str(r.get("team", "") or "")
        r["pos"] = pos.upper()
        r.pop("player", None)

        r = _numify_row(r)
        if "proj_pts" not in r:
            r["proj_pts"] = None

        if name:
            out.append(r)
    return out

# --------------------------
# Scrapers (main & printer)
# --------------------------
async def scrape_table(url: str, pos: str, headful: bool = False) -> List[Dict[str, object]]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headful)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded")

        # Dismiss common consent banners
        for label in ["Accept", "I Agree", "Got it", "Close", "OK"]:
            try:
                await page.get_by_role("button", name=label, exact=False).click(timeout=1200)
            except Exception:
                pass

        # Let lazy content load by scrolling a bit
        last_count, stable = -1, 0
        for _ in range(40):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(350)
            count = await page.evaluate("() => (document.querySelector('tbody') ? document.querySelector('tbody').querySelectorAll('tr').length : 0)")
            if count == last_count:
                stable += 1
            else:
                stable = 0
            last_count = count
            if stable >= 3:
                break

        data = await page.evaluate(JS_GET_TABLE)
        headers = data.get("headers") or []
        rows = data.get("rows") or []
        out = _rows_from_grouped_headers(headers, rows, pos)
        await browser.close()
        return out

async def scrape_printer(url: str, pos: str, headful: bool = False) -> List[Dict[str, object]]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headful)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded")

        opened = False
        for text in ["Printer Friendly", "Printer-Friendly", "Print"]:
            try:
                await page.get_by_text(text, exact=False).first.click(timeout=2000)
                opened = True
                break
            except Exception:
                pass
        if not opened:
            try:
                await page.goto(url + ("&" if "?" in url else "?") + "print=true", wait_until="domcontentloaded")
            except Exception:
                pass

        data = await page.evaluate(JS_GET_TABLE)
        headers = data.get("headers") or []
        rows = data.get("rows") or []
        out = _rows_from_grouped_headers(headers, rows, pos)
        await browser.close()
        return out

# --------------------------
# Writers
# --------------------------
def write_csv(rows: List[Dict[str, object]], out_path: str):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    # union of keys for header
    keys = set()
    for r in rows:
        keys.update(r.keys())
    preferred = ["player_name", "team", "pos", "proj_pts"]
    ordered = preferred + sorted([k for k in keys if k not in preferred])

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ordered)
        w.writeheader()
        for r in rows:
            w.writerow(r)

def upsert_sqlite(rows: List[Dict[str, object]], sqlite_path: str, *, season: int, week: str, pos: str, scoring: str):
    os.makedirs(os.path.dirname(os.path.abspath(sqlite_path)), exist_ok=True)
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fp_projections (
            season INTEGER,
            week_tag TEXT,     -- 'draft' or numeric
            scoring TEXT,      -- label (e.g., 'half_ppr')
            pos TEXT,          -- QB/RB/WR/TE/K/DST
            player_name TEXT,
            team TEXT,
            proj_pts REAL,
            stats_json TEXT,   -- all other numeric stats as JSON
            source TEXT DEFAULT 'FantasyPros',
            fetched_at TEXT,
            PRIMARY KEY (season, week_tag, scoring, pos, player_name)
        )
    """)
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        name = str(r.get("player_name", "") or "")
        team = str(r.get("team", "") or "")
        proj_pts = r.get("proj_pts")
        stats = {k: v for k, v in r.items() if k not in ("player_name", "team", "pos", "proj_pts")}
        cur.execute("""
            INSERT INTO fp_projections
              (season, week_tag, scoring, pos, player_name, team, proj_pts, stats_json, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'FantasyPros', ?)
            ON CONFLICT(season, week_tag, scoring, pos, player_name) DO UPDATE SET
              team=COALESCE(excluded.team, fp_projections.team),
              proj_pts=excluded.proj_pts,
              stats_json=excluded.stats_json,
              fetched_at=excluded.fetched_at
        """, (
            season, week, scoring, pos.upper(),
            name, team, proj_pts,
            json.dumps(stats, separators=(",", ":")),
            now
        ))
    conn.commit()
    conn.close()

# --------------------------
# Orchestrator
# --------------------------
async def fetch_for_position(pos: str, *, week: str, headful: bool) -> List[Dict[str, object]]:
    url = BASE_URL.format(pos=pos.lower(), week=week)
    # prefer main page (grouped headers)
    rows = await scrape_table(url, pos, headful=headful)
    if len(rows) < 25:  # suspiciously small → try printer-friendly
        rows = await scrape_printer(url, pos, headful=headful)
    return rows

async def main():
    ap = argparse.ArgumentParser(description="FantasyPros projections scraper (grouped headers → unique stat columns).")
    ap.add_argument("--positions", default="qb,rb,wr,te,k,dst", help="Comma-separated positions")
    ap.add_argument("--week", default="draft", help="draft or 1..18")
    ap.add_argument("--season", type=int, default=datetime.now().year)
    ap.add_argument("--scoring", default="half_ppr", help="Label only (stored in DB for context)")
    ap.add_argument("--out-csv-combined", default="./data/normalized/fp_projections_all.csv")
    ap.add_argument("--out-dir-pos", default="./data/normalized/projections_by_pos")
    ap.add_argument("--sqlite", default="./core/core.db")
    ap.add_argument("--no-sqlite", action="store_true")
    ap.add_argument("--headful", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.out_dir_pos, exist_ok=True)

    positions = [p.strip().lower() for p in args.positions.split(",") if p.strip()]
    all_rows: List[Dict[str, object]] = []

    for pos in positions:
        print(f"Fetching projections for {pos.upper()} (week={args.week})...")
        rows = await fetch_for_position(pos, week=args.week, headful=args.headful)
        print(f"  → {len(rows)} rows")
        if rows:
            out_pos_csv = os.path.join(args.out_dir_pos, f"fp_projections_{pos}_{args.week}.csv")
            write_csv(rows, out_pos_csv)
            if not args.no_sqlite:
                upsert_sqlite(rows, args.sqlite, season=args.season, week=args.week, pos=pos, scoring=args.scoring)
            all_rows.extend(rows)

    write_csv(all_rows, args.out_csv_combined)
    print(f"Combined CSV -> {args.out_csv_combined}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
