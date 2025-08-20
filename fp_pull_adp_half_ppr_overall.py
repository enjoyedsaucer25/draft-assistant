import asyncio, argparse, csv, os, re, sqlite3, sys
from datetime import datetime
from typing import Dict, List, Optional

# Dependencies:
#   pip install playwright
#   python -m playwright install chromium
from playwright.async_api import async_playwright

ADP_URL_DEFAULT = "https://www.fantasypros.com/nfl/adp/half-point-ppr-overall.php"

# -------------------------
# Helpers / Normalization
# -------------------------
def _norm_pos(p: Optional[str]) -> Optional[str]:
    if not p:
        return None
    return re.sub(r"\d+$", "", p.strip().upper())  # WR17 -> WR

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

def _to_int(x: str) -> Optional[int]:
    try:
        v = re.sub(r"[^\d]", "", x or "")
        return int(v) if v else None
    except:
        return None

def _to_float(x: str) -> Optional[float]:
    try:
        x = (x or "").replace(",", ".")
        m = re.search(r"\d+(?:\.\d+)?", x)
        return float(m.group(0)) if m else None
    except:
        return None

# -------------------------
# CSV Normalizer (ADP)
# -------------------------
def normalize_rows_from_csv_adp(path: str) -> List[Dict]:
    """
    Normalize FantasyPros ADP CSV (Half-PPR) to:
    player_name, adp_rank, pos, bye, adp_avg, adp_yahoo, adp_sleeper, adp_rtsports
    """
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        hdrs = {h.lower().strip(): h for h in (reader.fieldnames or [])}

        def pick(*cands):
            for c in cands:
                if c in hdrs:
                    return hdrs[c]
            return None

        col_rank   = pick("rk", "rank", "overall", "overall rank")
        col_player = pick("player", "player name", "player_name", "player team (bye)", "player/team", "player (team)")
        col_pos    = pick("pos", "position")
        col_bye    = pick("bye", "bye week")

        # average ADP column
        col_adp_avg = pick("adp", "avg", "average", "average draft position", "average draft position (adp)", "avg adp")

        # site-specific columns (FantasyPros sometimes varies a little)
        col_yahoo   = pick("yahoo", "adp (yahoo)", "yahoo adp")
        col_sleeper = pick("sleeper", "adp (sleeper)", "sleeper adp")
        col_rts     = pick("rtsports", "rt sports", "rts", "adp (rtsports)", "adp (rt sports)")

        out: List[Dict] = []
        for row in reader:
            raw_player = row.get(col_player, "").strip() if col_player else ""
            combo = raw_player

            name = _extract_name_from_combo(raw_player)
            adp_rank = _to_int(row.get(col_rank, "")) if col_rank else None

            if col_pos and row.get(col_pos):
                pos = _norm_pos(row[col_pos])
            else:
                m = re.search(r"\)\s+([A-Z]{2,5}\d*)$", combo)
                pos = _norm_pos(m.group(1)) if m else None

            if col_bye and row.get(col_bye):
                bye = re.sub(r"[^\d]", "", row[col_bye]).strip() or None
            else:
                bye = _extract_bye_from_combo(combo)

            adp_avg   = _to_float(row.get(col_adp_avg, "")) if col_adp_avg else None
            adp_yahoo = _to_float(row.get(col_yahoo, ""))   if col_yahoo   else None
            adp_sleep = _to_float(row.get(col_sleeper, "")) if col_sleeper else None
            adp_rts   = _to_float(row.get(col_rts, ""))     if col_rts     else None

            if name:
                out.append({
                    "player_name": name,
                    "adp_rank": adp_rank,
                    "pos": pos,
                    "bye": bye,
                    "adp_avg": adp_avg,
                    "adp_yahoo": adp_yahoo,
                    "adp_sleeper": adp_sleep,
                    "adp_rtsports": adp_rts
                })
        return out

# -------------------------
# Preferred: CSV downloader (via href)
# -------------------------
async def download_csv(url: str, save_to: str, headful: bool = False) -> Optional[str]:
    """
    Resolve the 'Download CSV' href and GET it. If not found, last-resort click+download.
    Returns saved file path or None.
    """
    from urllib.parse import urljoin
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headful)
        ctx = await browser.new_context(accept_downloads=True)
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded")

        # 1) Direct href
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

        # 2) Click + expect download
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
                final_path = save_to if not os.path.isdir(save_to) else os.path.join(
                    save_to, dl.suggested_filename or "fantasypros_adp_half_ppr.csv"
                )
                await dl.save_as(final_path)
                await browser.close()
                return final_path
        except Exception:
            pass

        await browser.close()
        return None

# -------------------------
# Scrape #1: main page (auto-expand)
# -------------------------
async def scrape_main_full_adp(url: str, headful: bool = False) -> List[Dict]:
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

        # Auto-expand: click "More/Next/Show all" and scroll till row count stabilizes
        last_count, stable_hits = -1, 0
        BTN = ["Show More", "Load More", "More", "Show all", "View all", "Next", "Show All", "See More"]
        for _ in range(60):
            clicked = False
            for label in BTN:
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

            # Scroll to bottom for lazy-load
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(800)

            count = await page.evaluate("""
            () => {
              const t = Array.from(document.querySelectorAll('table')).find(x => x.querySelector('thead'));
              return t ? t.querySelectorAll('tbody tr').length : 0;
            }
            """)
            if count == last_count:
                stable_hits += 1
            else:
                stable_hits = 0
            last_count = count
            if stable_hits >= 3:
                break

        # Extract table
        data = await page.evaluate("""
        () => {
          const t = Array.from(document.querySelectorAll('table')).find(x => x.querySelector('thead'));
          if (!t) return {headers: [], rows: []};
          const headers = Array.from(t.querySelectorAll('thead th, tr th')).map(x => x.innerText.trim().toLowerCase());
          const rows = Array.from(t.querySelectorAll('tbody tr')).map(tr => {
            const tds = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
            return tds;
          });
          return {headers, rows};
        }
        """)
        headers = data.get("headers") or []
        rows = data.get("rows") or []

        def idx_exact(*names):
            for n in names:
                try:
                    return headers.index(n)
                except ValueError:
                    pass
            return None

        def idx_contains(*substrs):
            for i, h in enumerate(headers):
                for s in substrs:
                    if s in h:
                        return i
            return None

        i_rank   = idx_exact('rk','rank','overall','overall rank')
        i_player = idx_exact('player','player name','player_name','player team (bye)','player/team','player (team)')
        if i_player is None:
            # Some tables use "player (team)" variants; fallback to contains
            i_player = idx_contains('player')
        i_pos    = idx_exact('pos','position')
        i_bye    = idx_exact('bye','bye week')

        # Average ADP & sites
        i_adp_avg = idx_exact('adp','avg','average','average draft position','average draft position (adp)','avg adp')
        i_yahoo   = idx_contains('yahoo')
        i_sleep   = idx_contains('sleeper')
        i_rts     = idx_contains('rtsports','rt sports','rts')

        out: List[Dict] = []
        for r in rows:
            if not r: 
                continue
            cell = lambda i: (r[i] if (i is not None and i < len(r)) else "").strip()

            player_cell = cell(i_player)
            if not player_cell:
                continue

            name = _extract_name_from_combo(player_cell)
            adp_rank = _to_int(cell(i_rank))
            pos = _norm_pos(cell(i_pos))
            bye = cell(i_bye) or _extract_bye_from_combo(player_cell)

            adp_avg   = _to_float(cell(i_adp_avg))
            adp_yahoo = _to_float(cell(i_yahoo))
            adp_sleep = _to_float(cell(i_sleep))
            adp_rts   = _to_float(cell(i_rts))

            out.append({
                "player_name": name,
                "adp_rank": adp_rank,
                "pos": pos,
                "bye": bye,
                "adp_avg": adp_avg,
                "adp_yahoo": adp_yahoo,
                "adp_sleeper": adp_sleep,
                "adp_rtsports": adp_rts
            })

        await browser.close()
        return out

# -------------------------
# Scrape #2: printer-friendly
# -------------------------
async def scrape_printer_friendly_adp(url: str, headful: bool = False) -> List[Dict]:
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
          const t = Array.from(document.querySelectorAll('table')).find(x => x.querySelector('thead'));
          if (!t) return {headers: [], rows: []};
          const headers = Array.from(t.querySelectorAll('thead th, tr th')).map(x => x.innerText.trim().toLowerCase());
          const rows = Array.from(t.querySelectorAll('tbody tr')).map(tr => {
            const tds = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
            return tds;
          });
          return {headers, rows};
        }
        """)
        headers = data.get("headers") or []
        rows = data.get("rows") or []

        def idx_exact(*names):
            for n in names:
                try:
                    return headers.index(n)
                except ValueError:
                    pass
            return None

        def idx_contains(*substrs):
            for i, h in enumerate(headers):
                for s in substrs:
                    if s in h:
                        return i
            return None

        i_rank   = idx_exact('rk','rank','overall','overall rank')
        i_player = idx_exact('player','player name','player_name','player team (bye)','player/team','player (team)')
        if i_player is None:
            i_player = idx_contains('player')
        i_pos    = idx_exact('pos','position')
        i_bye    = idx_exact('bye','bye week')

        i_adp_avg = idx_exact('adp','avg','average','average draft position','average draft position (adp)','avg adp')
        i_yahoo   = idx_contains('yahoo')
        i_sleep   = idx_contains('sleeper')
        i_rts     = idx_contains('rtsports','rt sports','rts')

        out: List[Dict] = []
        for r in rows:
            if not r: 
                continue
            cell = lambda i: (r[i] if (i is not None and i < len(r)) else "").strip()

            player_cell = cell(i_player)
            if not player_cell:
                continue

            name = _extract_name_from_combo(player_cell)
            adp_rank = _to_int(cell(i_rank))
            pos = _norm_pos(cell(i_pos))
            bye = cell(i_bye) or _extract_bye_from_combo(player_cell)

            adp_avg   = _to_float(cell(i_adp_avg))
            adp_yahoo = _to_float(cell(i_yahoo))
            adp_sleep = _to_float(cell(i_sleep))
            adp_rts   = _to_float(cell(i_rts))

            out.append({
                "player_name": name,
                "adp_rank": adp_rank,
                "pos": pos,
                "bye": bye,
                "adp_avg": adp_avg,
                "adp_yahoo": adp_yahoo,
                "adp_sleeper": adp_sleep,
                "adp_rtsports": adp_rts
            })

        await browser.close()
        return out

# -------------------------
# Writers
# -------------------------
def write_csv(rows: List[Dict], out_path: str):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["player_name","adp_rank","pos","bye","adp_avg","adp_yahoo","adp_sleeper","adp_rtsports"]
        )
        w.writeheader()
        w.writerows(rows)

def upsert_sqlite_adp(rows: List[Dict], sqlite_path: str, *, season: int, scoring: str = "half_ppr", view: str = "overall"):
    os.makedirs(os.path.dirname(os.path.abspath(sqlite_path)), exist_ok=True)
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fp_adp_half_ppr_overall (
            season INTEGER,
            scoring TEXT,          -- 'half_ppr'
            view TEXT,             -- 'overall'
            player_name TEXT,
            pos TEXT,
            bye TEXT,
            adp_rank INTEGER,
            adp_avg REAL,
            adp_yahoo REAL,
            adp_sleeper REAL,
            adp_rtsports REAL,
            source TEXT DEFAULT 'FantasyPros',
            fetched_at TEXT,
            PRIMARY KEY (season, scoring, view, player_name)
        )
    """)
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        cur.execute("""
            INSERT INTO fp_adp_half_ppr_overall
                (season, scoring, view, player_name, pos, bye, adp_rank, adp_avg, adp_yahoo, adp_sleeper, adp_rtsports, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'FantasyPros', ?)
            ON CONFLICT(season, scoring, view, player_name) DO UPDATE SET
                pos=COALESCE(excluded.pos, fp_adp_half_ppr_overall.pos),
                bye=COALESCE(excluded.bye, fp_adp_half_ppr_overall.bye),
                adp_rank=excluded.adp_rank,
                adp_avg=excluded.adp_avg,
                adp_yahoo=excluded.adp_yahoo,
                adp_sleeper=excluded.adp_sleeper,
                adp_rtsports=excluded.adp_rtsports,
                fetched_at=excluded.fetched_at
        """, (
            season, scoring, view, r["player_name"], r["pos"], r["bye"],
            r["adp_rank"], r["adp_avg"], r["adp_yahoo"], r["adp_sleeper"], r["adp_rtsports"], now
        ))
    conn.commit()
    conn.close()

# -------------------------
# Main
# -------------------------
async def main():
    ap = argparse.ArgumentParser(description="FantasyPros Half-PPR Overall ADP: CSV-first with full-page & printer-friendly fallbacks")
    ap.add_argument("--url", default=ADP_URL_DEFAULT)
    ap.add_argument("--download-to", default="./data/raw/fp_adp_half_ppr_overall.csv")
    ap.add_argument("--out-csv", default="./data/normalized/fp_adp_half_ppr_overall_normalized.csv")
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
        rows = normalize_rows_from_csv_adp(downloaded)
    else:
        # 2) Main page full scrape
        print("CSV not available; scraping main page (expanding table)...")
        rows = await scrape_main_full_adp(args.url, headful=args.headful)
        if len(rows) < 100:
            print(f"Only {len(rows)} rows from main page; trying Printer-Friendly fallback...")
            rows = await scrape_printer_friendly_adp(args.url, headful=args.headful)

    # Final guard: drop empties
    rows = [r for r in rows if r.get("player_name")]

    print(f"Parsed {len(rows)} ADP rows")
    write_csv(rows, args.out_csv)
    print(f"Normalized CSV -> {args.out_csv}")

    if not args.no_sqlite:
        upsert_sqlite_adp(rows, args.sqlite, season=args.season, scoring="half_ppr", view="overall")
        print(f"Upserted into SQLite -> {args.sqlite} (table: fp_adp_half_ppr_overall)")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
