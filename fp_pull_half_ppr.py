import asyncio, argparse, csv, os, re, sqlite3, sys
from datetime import datetime
from typing import Dict, List, Optional

# pip install playwright
# python -m playwright install chromium
from playwright.async_api import async_playwright

CHEATSHEET_URL = "https://www.fantasypros.com/nfl/rankings/half-point-ppr-cheatsheets.php"

# -------------------------
# Helpers / Normalization
# -------------------------
def _norm_pos(p: Optional[str]) -> Optional[str]:
    if not p:
        return None
    return re.sub(r"\d+$", "", p.strip().upper())  # WR1 -> WR

def _extract_bye_from_combo(s: str) -> Optional[str]:
    m = re.search(r"\((\d{1,2})\)", s or "")
    return m.group(1) if m else None

def _extract_name_from_combo(s: str) -> str:
    s = (s or "").strip()
    # "Justin Jefferson MIN (6) WR2" -> "Justin Jefferson"
    s = re.split(r"\s+[A-Z]{2,3}\s+\(\d{1,2}\)\s+[A-Z]{2,5}\d*", s)[0].strip()
    # "Ja'Marr Chase (CIN)" -> "Ja'Marr Chase"
    s = re.sub(r"\s+\([A-Z]{2,3}\)$", "", s)
    return s.strip()

def normalize_rows_from_csv(path: str) -> List[Dict]:
    """Return list of dicts: player_name, rank, tier, pos, bye."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        hdrs = {h.lower().strip(): h for h in (reader.fieldnames or [])}

        def pick(*cands):
            for c in cands:
                if c in hdrs:
                    return hdrs[c]
            return None

        col_rank   = pick("rk", "rank", "ecr")
        col_player = pick("player", "player name", "player_name", "player team (bye)", "player/team", "player (team)")
        col_tier   = pick("tier", "tiers")          # may be blank
        col_pos    = pick("pos", "position")
        col_bye    = pick("bye", "bye week")

        out: List[Dict] = []
        for row in reader:
            raw_player = row.get(col_player, "").strip() if col_player else ""
            combo = raw_player
            player_name = _extract_name_from_combo(raw_player)

            def to_int(x: str) -> Optional[int]:
                try:
                    v = int(re.sub(r"[^\d]", "", x or ""))
                    return v
                except:
                    return None

            rank = to_int(row.get(col_rank, "")) if col_rank else None
            tier = to_int(row.get(col_tier, "")) if col_tier else None

            if col_pos and row.get(col_pos):
                pos = _norm_pos(row[col_pos])
            else:
                m = re.search(r"\)\s+([A-Z]{2,5}\d*)$", combo)
                pos = _norm_pos(m.group(1)) if m else None

            if col_bye and row.get(col_bye):
                bye = re.sub(r"[^\d]", "", row[col_bye]).strip() or None
            else:
                bye = _extract_bye_from_combo(combo)

            out.append({"player_name": player_name, "rank": rank, "tier": tier, "pos": pos, "bye": bye})
        return out

# -------------------------
# Tier propagation (CSV or scrape)
# -------------------------
TIER_NAME_RE = re.compile(r"(?i)^\s*(?:customize\s+tiers|tier)\s*(\d+)?\s*$")

def apply_tier_propagation(rows: List[Dict], keep_headers: bool = False) -> List[Dict]:
    out: List[Dict] = []
    current_tier: Optional[int] = None

    for r in rows:
        name = (r.get("player_name") or "").strip()
        rank = r.get("rank")

        # Header rows like "Customize Tiers 2" or "Tier 3"
        m = TIER_NAME_RE.match(name)
        if m:
            tier_from_name = m.group(1)
            if tier_from_name and tier_from_name.isdigit():
                current_tier = int(tier_from_name)
            elif isinstance(rank, int):
                current_tier = rank
            else:
                current_tier = None
            if keep_headers:
                out.append({"player_name": "Customize Tiers", "rank": current_tier, "tier": current_tier, "pos": None, "bye": None})
            continue

        if r.get("tier") is None:
            r["tier"] = current_tier

        if name:
            out.append(r)
    return out

# -------------------------
# Preferred: CSV
# -------------------------
async def download_csv(url: str, save_to: str, headful: bool = False) -> Optional[str]:
    """Fetch the CSV via href if available; fallback to click+download event."""
    from urllib.parse import urljoin

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headful)
        ctx = await browser.new_context(accept_downloads=True)
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded")

        # direct href
        for sel in ["a:has-text('Download CSV')", "a[href$='.csv']", "a[href*='download'][href*='csv']", "a[download*='csv']"]:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    href = await loc.get_attribute("href")
                    if href:
                        csv_url = urljoin(page.url, href)
                        resp = await ctx.request.get(csv_url)
                        if resp.ok:
                            os.makedirs(os.path.dirname(os.path.abspath(save_to)), exist_ok=True)
                            with open(save_to, "wb") as f:
                                f.write(await resp.body())
                            await browser.close()
                            return save_to
            except Exception:
                pass

        # click + download
        try:
            for sel in ["text=Download CSV", "a:has-text('Download CSV')", "button:has-text('Download CSV')", "a[download*='csv']"]:
                loc = page.locator(sel).first
                if await loc.count() == 0:
                    continue
                await loc.scroll_into_view_if_needed()
                async with page.expect_download(timeout=45000) as dl_info:
                    await loc.click()
                dl = await dl_info.value
                os.makedirs(os.path.dirname(os.path.abspath(save_to)), exist_ok=True)
                final_path = save_to if not os.path.isdir(save_to) else os.path.join(save_to, dl.suggested_filename or "fantasypros.csv")
                await dl.save_as(final_path)
                await browser.close()
                return final_path
        except Exception:
            pass

        await browser.close()
        return None

# -------------------------
# Scrape #1: main page (auto-expand to get ALL rows)
# -------------------------
async def scrape_main_full(url: str, headful: bool = False) -> List[Dict]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headful)
        ctx = await pw.chromium.launch_persistent_context(user_data_dir="", headless=not headful) if False else await pw.chromium.launch(headless=not headful)  # simple
        # use normal context
        await browser.close()  # clean the accidental one above
        browser = await pw.chromium.launch(headless=not headful)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded")

        # try dismiss common consent banners
        for label in ["Accept", "I Agree", "Got it", "Close", "OK"]:
            try:
                await page.get_by_role("button", name=label, exact=False).click(timeout=1200)
            except Exception:
                pass

        # loop: try to expand until row count stops growing
        last_count = -1
        stable_hits = 0
        BUTTON_LABELS = ["Show More", "Load More", "More", "Show all", "View all", "Next", "Show All", "See More"]
        for _ in range(60):  # hard cap
            # try clicking any visible "more/next"
            clicked = False
            for label in BUTTON_LABELS:
                try:
                    btn = page.get_by_role("button", name=label, exact=False).first
                    if await btn.count() > 0 and await btn.is_enabled():
                        await btn.scroll_into_view_if_needed()
                        await btn.click(timeout=1200)
                        clicked = True
                        await page.wait_for_timeout(700)
                        break
                except Exception:
                    pass

            # also try common link-style controls
            if not clicked:
                for label in ["Next", "More", "Show More", "Show All"]:
                    try:
                        lnk = page.get_by_role("link", name=label, exact=False).first
                        if await lnk.count() > 0:
                            await lnk.scroll_into_view_if_needed()
                            await lnk.click(timeout=1200)
                            clicked = True
                            await page.wait_for_timeout(700)
                            break
                    except Exception:
                        pass

            # scroll to bottom to trigger lazy-load, even if we didn't click
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(800)

            # check current count
            count = await page.evaluate("""
            () => {
              const t = Array.from(document.querySelectorAll('table')).find(x => x.querySelector('thead'));
              if (!t) return 0;
              return t.querySelectorAll('tbody tr').length;
            }
            """)
            if count == last_count:
                stable_hits += 1
            else:
                stable_hits = 0
            last_count = count
            if stable_hits >= 3:  # stable for 3 cycles -> assume fully loaded
                break

        # extract rows (including any tier headers in the flow)
        data = await page.evaluate("""
        () => {
          const t = Array.from(document.querySelectorAll('table')).find(x => x.querySelector('thead'));
          if (!t) return {headers: [], rows: []};
          const headers = Array.from(t.querySelectorAll('thead th, tr th')).map(x => x.innerText.trim().toLowerCase());
          const body = Array.from(t.querySelectorAll('tbody tr'));
          const rows = body.map(tr => {
            const tds = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
            const txt = tr.innerText.trim();
            return {cells: tds, full: txt};
          });
          return {headers, rows};
        }
        """)
        headers = data.get("headers") or []
        rowsraw = data.get("rows") or []

        def idx(*names):
            for n in names:
                if n in headers:
                    return headers.index(n)
            return None

        i_rank   = idx('rk','rank')
        i_tier   = idx('tier','tiers')   # may exist
        i_pos    = idx('pos','position')
        i_player = idx('player','player name','player_name','player team (bye)','player/team','player (team)')
        i_bye    = idx('bye','bye week')

        out: List[Dict] = []
        current_tier: Optional[int] = None
        TIER_INLINE_RE = re.compile(r"(?i)(?:customize\s+tiers|tier)\s*(\d+)")

        for rr in rowsraw:
            cells = rr["cells"]; full = rr["full"] or ""
            cell = lambda i: (cells[i] if (i is not None and i < len(cells)) else "").strip()

            m = TIER_INLINE_RE.search(full)
            if m:
                try:
                    current_tier = int(m.group(1))
                except:
                    current_tier = None
                continue

            player_cell = cell(i_player)
            if not player_cell:
                continue

            name = _extract_name_from_combo(player_cell)
            bye  = cell(i_bye) or _extract_bye_from_combo(player_cell)
            pos  = _norm_pos(cell(i_pos))

            def to_int(x: str) -> Optional[int]:
                try:
                    v = re.sub(r"[^\d]", "", x or "")
                    return int(v) if v else None
                except:
                    return None

            rank = to_int(cell(i_rank))
            tier = to_int(cell(i_tier)) if i_tier is not None else None
            if tier is None:
                tier = current_tier

            out.append({"player_name": name, "rank": rank, "tier": tier, "pos": pos, "bye": bye})

        await browser.close()
        return out

# -------------------------
# Scrape #2: printer-friendly (fallback)
# -------------------------
async def scrape_printer_friendly(url: str, headful: bool = False) -> List[Dict]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headful)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded")

        # Try printer-friendly; else ?print=true
        opened_print = False
        for text in ["Printer Friendly", "Printer-Friendly", "Print"]:
            try:
                await page.get_by_text(text, exact=False).first.click(timeout=2500)
                opened_print = True
                break
            except Exception:
                pass
        if not opened_print:
            try:
                await page.goto(url + ("&" if "?" in url else "?") + "print=true", wait_until="domcontentloaded")
            except Exception:
                pass

        await page.wait_for_timeout(800)

        data = await page.evaluate("""
        () => {
          const table = Array.from(document.querySelectorAll('table')).find(t => t.querySelector('thead'));
          if (!table) return {headers: [], rows: []};
          const headers = Array.from(table.querySelectorAll('thead th, tr th')).map(x => x.innerText.trim().toLowerCase());
          const rows = Array.from(table.querySelectorAll('tbody tr')).map(tr => {
            const tds = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
            const txt = tr.innerText.trim();
            return {cells: tds, full: txt};
          });
          return {headers, rows};
        }
        """)
        headers = data.get("headers") or []
        rowsraw = data.get("rows") or []

        def idx(*names):
            for n in names:
                if n in headers:
                    return headers.index(n)
            return None

        i_rank   = idx('rk','rank')
        i_tier   = idx('tier','tiers')
        i_pos    = idx('pos','position')
        i_player = idx('player','player name','player_name','player team (bye)','player/team','player (team)')
        i_bye    = idx('bye','bye week')

        out: List[Dict] = []
        current_tier: Optional[int] = None
        TIER_INLINE_RE = re.compile(r"(?i)(?:customize\s+tiers|tier)\s*(\d+)")

        for rr in rowsraw:
            cells = rr["cells"]; full = rr["full"] or ""
            cell = lambda i: (cells[i] if (i is not None and i < len(cells)) else "").strip()

            m = TIER_INLINE_RE.search(full)
            if m:
                try:
                    current_tier = int(m.group(1))
                except:
                    current_tier = None
                continue

            player_cell = cell(i_player)
            if not player_cell:
                continue

            name = _extract_name_from_combo(player_cell)
            bye  = cell(i_bye) or _extract_bye_from_combo(player_cell)
            pos  = _norm_pos(cell(i_pos))

            def to_int(x: str) -> Optional[int]:
                try:
                    v = re.sub(r"[^\d]", "", x or "")
                    return int(v) if v else None
                except:
                    return None

            rank = to_int(cell(i_rank))
            tier = to_int(cell(i_tier)) if i_tier is not None else None
            if tier is None:
                tier = current_tier

            out.append({"player_name": name, "rank": rank, "tier": tier, "pos": pos, "bye": bye})

        await browser.close()
        return out

# -------------------------
# Writers
# -------------------------
def write_csv(rows: List[Dict], out_path: str):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["player_name","rank","tier","pos","bye"])
        w.writeheader()
        w.writerows(rows)

def upsert_sqlite(rows: List[Dict], sqlite_path: str, *, season: int, scoring: str, view: str):
    os.makedirs(os.path.dirname(os.path.abspath(sqlite_path)), exist_ok=True)
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fp_consensus_rankings (
            season INTEGER,
            scoring TEXT,
            view TEXT,
            player_name TEXT,
            rank INTEGER,
            tier INTEGER,
            pos TEXT,
            bye TEXT,
            source TEXT DEFAULT 'FantasyPros',
            fetched_at TEXT,
            PRIMARY KEY (season, scoring, view, player_name)
        )
    """)
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        cur.execute("""
            INSERT INTO fp_consensus_rankings (season, scoring, view, player_name, rank, tier, pos, bye, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'FantasyPros', ?)
            ON CONFLICT(season, scoring, view, player_name) DO UPDATE SET
                rank=excluded.rank,
                tier=COALESCE(excluded.tier, fp_consensus_rankings.tier),
                pos=COALESCE(excluded.pos, fp_consensus_rankings.pos),
                bye=COALESCE(excluded.bye, fp_consensus_rankings.bye),
                fetched_at=excluded.fetched_at
        """, (season, scoring, view, r["player_name"], r["rank"], r["tier"], r["pos"], r["bye"], now))
    conn.commit()
    conn.close()

# -------------------------
# Main
# -------------------------
async def main():
    ap = argparse.ArgumentParser(description="FantasyPros Half-PPR Overall: CSV-first, full-page scrape fallback with tier propagation")
    ap.add_argument("--url", default=CHEATSHEET_URL)
    ap.add_argument("--download-to", default="./data/raw/fp_half_ppr_overall.csv")
    ap.add_argument("--out-csv", default="./data/normalized/fp_half_ppr_overall_normalized.csv")
    ap.add_argument("--sqlite", default="./core/core.db")
    ap.add_argument("--season", type=int, default=datetime.now().year)
    ap.add_argument("--no-sqlite", action="store_true")
    ap.add_argument("--headful", action="store_true", help="Show browser window (debug)")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.download_to)), exist_ok=True)

    # 1) CSV (ideal)
    downloaded = await download_csv(args.url, args.download_to, headful=args.headful)
    if downloaded:
        print(f"Downloaded CSV -> {downloaded}")
        rows = normalize_rows_from_csv(downloaded)
    else:
        # 2) Main page full scrape
        print("CSV not available; scraping main page (expanding table)...")
        rows = await scrape_main_full(args.url, headful=args.headful)
        if len(rows) < 100:
            print(f"Only {len(rows)} rows from main page; trying Printer-Friendly fallback...")
            rows = await scrape_printer_friendly(args.url, headful=args.headful)

    # 3) Ensure tiers filled and header rows removed
    rows = apply_tier_propagation(rows, keep_headers=False)

    print(f"Parsed {len(rows)} player rows")
    write_csv(rows, args.out_csv)
    print(f"Normalized CSV -> {args.out_csv}")

    if not args.no_sqlite:
        upsert_sqlite(rows, args.sqlite, season=args.season, scoring="half_ppr", view="overall")
        print(f"Upserted into SQLite -> {args.sqlite} (table: fp_consensus_rankings)")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
