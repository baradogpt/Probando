import sys
import time
import re
from pathlib import Path
from datetime import datetime

import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.common.exceptions import TimeoutException

DATA_DIR = Path(r"C:\Proyectos\Pruebas\scrapeo\data")
HTML_ROOT = DATA_DIR / "html" / "whoscored"
PROFILE_DIR = r"C:\Proyectos\Pruebas\scrapeo\chrome_session"

LEAGUE = "ESP-La Liga"
SEASON = "2022-2023"


def _save_html(rel_path: str, html: str) -> None:
    path = HTML_ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(html or "", encoding="utf-8")
    except Exception:
        pass


def _normalize_date_text(text: str) -> str | None:
    text = text.strip()
    for fmt in ["%A, %b %d %Y", "%a, %b %d %Y", "%d %b %Y"]:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except Exception:
            pass
    return None


def _parse_match_card(text: str) -> dict | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 5:
        return None
    date_text = _normalize_date_text(lines[0]) or lines[0]
    noise = {"1", "X", "2", "-"}
    odds_re = re.compile(r"^\d+(?:\.\d+)?$")
    time_re = re.compile(r"^\d{1,2}:\d{2}$")
    team_candidates: list = []
    time_text = None
    for token in lines[1:]:
        if time_text is None and time_re.match(token):
            time_text = token
            continue
        if token in noise or odds_re.match(token):
            continue
        if token.isdigit():
            continue
        if token not in team_candidates:
            team_candidates.append(token)
        if len(team_candidates) >= 2:
            break
    if len(team_candidates) < 2:
        return None
    start_time = None
    if date_text and time_text:
        start_time = f"{date_text}T{time_text}:00"
    return {
        "date": date_text,
        "start_time": start_time,
        "home_team": team_candidates[0],
        "away_team": team_candidates[1],
    }


def _extract_from_dom(driver, league: str, season) -> list[dict]:
    rows = []
    seen_game_ids: set = set()
    
    cards = driver.execute_script(
        r"""
        const anchors = Array.from(document.querySelectorAll('a[href*="/matches/"][href*="/show/"]'));
        return anchors.map(a => {
          const match = a.href.match(/\/matches\/(\d+)\/show\//);
          const card = a.closest('div[class*="Match-module_match__"]');
          const panel = a.closest('div[class*="Accordion-module_accordion__"]');
          return {
            href: a.href,
            text: (card ? card.innerText : a.innerText) || '',
            dateText: (panel ? panel.innerText : '') || '',
            matchId: match ? match[1] : null,
          };
        });
        """
    ) or []
    
    for card in cards:
        mid_raw = card.get("matchId")
        href = str(card.get("href") or "")
        if not mid_raw:
            continue
        game_id = int(mid_raw)
        if game_id in seen_game_ids:
            continue
        parsed = _parse_match_card(str(card.get("text") or "")) or {}
        date_text = str(card.get("dateText") or "").splitlines()[0].strip() if card.get("dateText") else ""
        date = _normalize_date_text(date_text) or date_text
        start_time = parsed.get("start_time")
        home_team = parsed.get("home_team")
        away_team = parsed.get("away_team")
        if not home_team or not away_team:
            continue
        rows.append(
            {
                "date": date,
                "home_team": home_team,
                "away_team": away_team,
                "game_id": game_id,
                "url": href,
                "start_time": start_time,
                "score": None,
                "league": league,
                "season": season,
            }
        )
        seen_game_ids.add(game_id)
    return rows


def _current_label(driver) -> str:
    try:
        return driver.find_element(By.CSS_SELECTOR, "#toggleCalendar span.toggleDatePicker").text.strip()
    except Exception:
        return ""


def _collect_direction(driver, button_id: str, league: str, season, all_rows: list):
    seen_labels: set = set()
    while True:
        label = _current_label(driver)
        if label and label in seen_labels:
            break
        if label:
            seen_labels.add(label)
            safe_label = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("_") or "page"
            dom_html = driver.execute_script("return document.documentElement.outerHTML")
            _save_html(f"matches/{season}/calendario/{safe_label}.html", dom_html or "")
        
        rows = _extract_from_dom(driver, league, season)
        if rows:
            all_rows.extend(rows)
            print(f"  Found {len(rows)} matches for {label}")
        
        try:
            btn = driver.find_element(By.ID, button_id)
        except Exception:
            break
        if btn.get_attribute("disabled"):
            break
        prev_label = label
        driver.execute_script("arguments[0].click();", btn)
        try:
            WebDriverWait(driver, 30, poll_frequency=1).until(lambda d: _current_label(d) != prev_label)
        except TimeoutException:
            break
        time.sleep(1)


def _local_season_catalog(league: str) -> dict[str, str]:
    candidates = [
        HTML_ROOT / "seasons" / f"{league}.html",
    ]
    html_path = next((p for p in candidates if p.exists()), None)
    if html_path is None:
        return {}
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    matches = re.findall(r'<option[^>]*value="([^"]+)"[^>]*>(\d{4}/\d{4})</option>', html)
    catalog = {}
    for url, label in matches:
        text = str(label).strip()
        key = text.replace("/", "-")
        catalog[key] = url
    return catalog


def _local_fixtures_url(league: str, season: str) -> str | None:
    candidates = [
        HTML_ROOT / "seasons" / f"{league}.html",
    ]
    html_path = next((p for p in candidates if p.exists()), None)
    if html_path is None:
        return None
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    season_key = str(season).replace("/", "-")
    m = re.search(rf'<a[^>]*href="([^"]*/fixtures/[^"]*{re.escape(season_key)}[^"]*)"[^>]*class=""', html)
    if m:
        return m.group(1)
    m = re.search(r'<a[^>]*id="link-fixtures"[^>]*href="([^"]+)"', html)
    return m.group(1) if m else None


def main():
    print(f"Starting Chrome with profile: {PROFILE_DIR}")
    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.add_argument("--disable-gpu")
    
    driver = uc.Chrome(options=options, version_main=146)
    driver.implicitly_wait(15)
    
    season_str = str(SEASON).replace("/", "-")
    league_catalog = _local_season_catalog(LEAGUE)
    fixtures_url = _local_fixtures_url(LEAGUE, SEASON)
    season_url = league_catalog.get(season_str)
    
    league_urls = {
        "ESP-La Liga": "/regions/206/tournaments/4/seasons/9149/stages/21073/fixtures/spain-laliga-2022-2023",
    }
    
    fixtures_url = league_urls.get(LEAGUE) or fixtures_url
    
    if not fixtures_url:
        print(f"No fixtures URL found for {LEAGUE} {SEASON}")
        driver.quit()
        return
    
    url = f"https://www.whoscored.com{fixtures_url}"
    print(f"Loading: {url}")
    driver.get(url)
    
    try:
        WebDriverWait(driver, 30, poll_frequency=1).until(
            ec.presence_of_element_located((By.CSS_SELECTOR, '[data-hypernova-key="tournamentfixtures"]'))
        )
    except TimeoutException:
        print("Warning: page did not load fully, continuing...")
        time.sleep(5)
    
    _save_html(f"seasons/{LEAGUE}.html", driver.page_source)
    
    all_rows = []
    _collect_direction(driver, "dayChangeBtn-prev", LEAGUE, season_str, all_rows)
    driver.get(url)
    time.sleep(3)
    _save_html(f"seasons/{LEAGUE}.html", driver.page_source)
    _collect_direction(driver, "dayChangeBtn-next", LEAGUE, season_str, all_rows)
    
    driver.quit()
    
    if not all_rows:
        print("No matches found!")
        return
    
    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates(subset=["game_id"])
    print(f"Total unique matches: {len(df)}")

    csv_path = DATA_DIR / "html" / "whoscored" / "matches" / season_str / "schedule.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    print(f"Saved to: {csv_path}")
    
    aug_matches = df[df["date"].str.startswith("2022-08", na=False)]
    print(f"August 2022 matches: {len(aug_matches)}")
    for _, row in aug_matches.iterrows():
        print(f"  {row['game_id']}: {row['home_team']} vs {row['away_team']} ({row['date']})")


if __name__ == "__main__":
    main()