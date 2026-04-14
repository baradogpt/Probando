import sys
import time
from pathlib import Path
import re

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

DATA_DIR = Path(r"C:\Proyectos\Pruebas\scrapeo\data")
HTML_ROOT = DATA_DIR / "html" / "whoscored" / "matches" / "2022-2023"
PROFILE_DIR = r"C:\Proyectos\Pruebas\scrapeo\chrome_session"


def _save_html(rel_path: str, html: str) -> None:
    path = HTML_ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(html or "", encoding="utf-8")
    except Exception:
        pass


def _click_tab(label: str, driver) -> bool:
    candidates = []
    if label.startswith("#"):
        candidates.append(f"//a[@href='{label}']")
    candidates.extend([
        f"//a[normalize-space()='{label}']",
        f"//button[normalize-space()='{label}']",
        f"//*[self::li or self::span][normalize-space()='{label}']",
    ])
    for xpath in candidates:
        try:
            el = driver.find_element(By.XPATH, xpath)
            driver.execute_script("arguments[0].click();", el)
            time.sleep(2)
            return True
        except Exception:
            continue
    return False


def scrape_match(match_id: int, driver):
    match_root = str(match_id)
    show_url = f"https://www.whoscored.com/matches/{match_id}/show/"
    
    print(f"  {match_id}: show")
    driver.get(show_url)
    time.sleep(3)
    _save_html(f"{match_root}/show.html", driver.page_source)
    
    team_url = show_url.replace("/show/", "/teamstatistics/")
    print(f"  {match_id}: team")
    driver.get(team_url)
    time.sleep(2)
    _save_html(f"{match_root}/teamstatistics.html", driver.page_source)
    
    live_url = show_url.replace("/show/", "/livestatistics/")
    print(f"  {match_id}: live")
    driver.get(live_url)
    time.sleep(2)
    _save_html(f"{match_root}/livestatistics.html", driver.page_source)
    
    for side in ["home", "away"]:
        for tab in ["summary", "offensive", "defensive", "passing"]:
            frag = f"#live-player-{side}-{tab}"
            if _click_tab(frag, driver):
                html = driver.execute_script("return document.documentElement.outerHTML")
                _save_html(f"{match_root}/livestatistics_{side}_{tab}.html", html if isinstance(html, str) else str(html))
    
    live_show = show_url.replace("/show/", "/live/")
    print(f"  {match_id}: live2")
    driver.get(live_show)
    time.sleep(2)
    _save_html(f"{match_root}/live.html", driver.page_source)
    
    print(f"  {match_id} DONE")


def main():
    profile_dir = r"C:\Proyectos\Pruebas\scrapeo\chrome_session"
    
    print("Starting Chrome...")
    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--disable-gpu")
    
    driver = uc.Chrome(options=options, version_main=146)
    driver.implicitly_wait(15)
    
    import pandas as pd
    schedule = pd.read_csv(DATA_DIR / "html/whoscored/matches/2022-2023/schedule.csv")
    apr_schedule = schedule[schedule["date"].str.startswith("2023-04", na=False)]
    apr_matches = set(apr_schedule["game_id"].tolist())
    
    saved_ids = {int(p.name) for p in HTML_ROOT.iterdir() if p.is_dir() and p.name.isdigit()}
    missing = sorted(apr_matches - saved_ids)
    
    print(f"Missing: {len(apr_matches)} April matches")
    
    done = 0
    for mid in missing:
        try:
            scrape_match(mid, driver)
            done += 1
            print(f"Progress: {done}/{len(missing)}")
        except Exception as e:
            print(f"ERROR {mid}: {e}")
            break
    
    driver.quit()
    print(f"DONE: {done} matches scraped")


if __name__ == "__main__":
    main()