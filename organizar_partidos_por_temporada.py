import os
import re
import shutil
import json
import unicodedata
from pathlib import Path
from datetime import datetime, timedelta

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
FBREF_BASE = PROJECT_DIR / "data" / "html" / "fbref" / "ESP-La_Liga"
UNDERSTAT_BASE = PROJECT_DIR / "data" / "html" / "understat" / "ESP-La Liga"

def remove_accents(text):
    if not text:
        return text
    normalized = unicodedata.normalize('NFD', text)
    return ''.join(c for c in normalized if unicodedata.category(c) != 'Mn').lower().strip()

def normalize_team_name(name):
    if not name:
        return None
    name = remove_accents(name)
    
    mappings = {
        "real valladolid": "valladolid",
        "real oviedo": "oviedo",
        "real sociedad": "sociedad",
        "real madrid": "real madrid",
        "real betis": "betis",
        "celta vigo": "celta vigo",
        "athletic club": "athletic",
        "atlético madrid": "atletico madrid",
        "athletic": "athletic",
        "rayo vallecano": "rayo",
        "alavés": "alaves",
        "almeria": "almeria",
        "deportivo": "deportivo",
        "leganés": "leganes",
        "las palmas": "las palmas",
        "granada": "granada",
    }
    return mappings.get(name, name)

def get_match_info_from_fbref(match_file):
    content = match_file.read_text(encoding='utf-8', errors='ignore')
    
    jornada_match = re.search(r'Matchweek\s+(\d+)', content)
    jornada = int(jornada_match.group(1)) if jornada_match else 0
    
    date_match = re.search(r'data-venue-date="(\d{4}-\d{2}-\d{2})"', content)
    match_date = date_match.group(1) if date_match else None
    
    teams_match = re.search(r'/en/matches/[^/]+/([^/]+)-vs-([^/]+)-', content)
    if not teams_match:
        teams_match = re.search(r'<strong>([^/]+) vs\. ([^<]+) Match Report', content)
    
    if teams_match:
        home_team = normalize_team_name(teams_match.group(1).strip())
        away_team = normalize_team_name(teams_match.group(2).strip())
    else:
        home_team = None
        away_team = None
    
    return jornada, match_date, home_team, away_team

def build_fbref_index(season_dir):
    index = {}
    match_files = list(season_dir.glob("match_*.html"))
    
    for jornada_folder in season_dir.glob("jornada_*"):
        if jornada_folder.is_dir():
            match_files.extend(jornada_folder.glob("match_*.html"))
    
    for match_file in match_files:
        jornada, match_date, home_team, away_team = get_match_info_from_fbref(match_file)
        
        if match_date and home_team and away_team:
            # Store for exact match and for fuzzy matching (±1 day)
            index[(match_date, home_team, away_team)] = jornada
    
    return index

def find_jornada(fbref_index, match_date, home_team, away_team):
    """Find jornada with fuzzy date matching (±1 day)"""
    # Try exact match first
    key = (match_date, home_team, away_team)
    if key in fbref_index:
        return fbref_index[key]
    
    # Try ±1 day
    from datetime import datetime, timedelta
    try:
        dt = datetime.strptime(match_date, "%Y-%m-%d")
        
        # Try previous day
        prev_day = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
        key = (prev_day, home_team, away_team)
        if key in fbref_index:
            return fbref_index[key]
        
        # Try next day
        next_day = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
        key = (next_day, home_team, away_team)
        if key in fbref_index:
            return fbref_index[key]
    except:
        pass
    
    return None

def process_fbref_season(season_dir):
    print(f"FBREF: {season_dir.name}")
    
    jornada_folders = list(season_dir.glob("jornada_*"))
    if jornada_folders:
        print(f"  Ya organizado en {len(jornada_folders)} jornadas")
        return
    
    match_files = sorted(season_dir.glob("match_*.html"))
    if not match_files:
        print(f"  Sin archivos de partidos")
        return
    
    for match_file in match_files:
        jornada, _, _, _ = get_match_info_from_fbref(match_file)
        jornada_folder = season_dir / f"jornada_{jornada}"
        jornada_folder.mkdir(parents=True, exist_ok=True)
        shutil.move(str(match_file), str(jornada_folder / match_file.name))
    
    print(f"  Organizado en jornadas")

def process_understat_season(season_dir, fbref_index, season_name):
    print(f"UNDERSTAT: {season_name}")
    
    jornada_folders = list(season_dir.glob("jornada_*"))
    if jornada_folders:
        print(f"  Ya organizado en {len(jornada_folders)} jornadas")
        return
    
    matches_dir = season_dir / "matches"
    if not matches_dir.exists():
        print(f"  Sin directorio de partidos")
        return
    
    json_files = list(matches_dir.glob("*.json"))
    league_file = season_dir / "league.json"
    if league_file in json_files:
        json_files.remove(league_file)
    
    if not json_files:
        print(f"  Sin archivos de partidos")
        return
    
    matched = 0
    unmatched = []
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            unmatched.append(json_file.name)
            continue
        
        jornada = None
        
        if 'shots' in data and 'h' in data['shots'] and data['shots']['h']:
            first_shot = data['shots']['h'][0]
            match_date = first_shot.get('date', '')[:10]
            home_team = normalize_team_name(first_shot.get('h_team', ''))
            away_team = normalize_team_name(first_shot.get('a_team', ''))
            
        jornada = find_jornada(fbref_index, match_date, home_team, away_team)
        
        if jornada is None:
            unmatched.append(json_file.name)
            continue
        
        matched += 1
        jornada_folder = season_dir / f"jornada_{jornada}"
        jornada_folder.mkdir(parents=True, exist_ok=True)
        shutil.move(str(json_file), str(jornada_folder / json_file.name))
    
    print(f"  {matched} partidos organizados, {len(unmatched)} sin matchear")

def main():
    fbref_seasons = [d for d in FBREF_BASE.iterdir() if d.is_dir() and d.name.startswith("20")]
    
    print("=== FBREF ===")
    for season_dir in fbref_seasons:
        process_fbref_season(season_dir)
    
    print("\n=== UNDERSTAT ===")
    for season_dir in fbref_seasons:
        season_name = season_dir.name
        understat_dir = UNDERSTAT_BASE / season_name
        
        if not understat_dir.exists():
            print(f"UNDERSTAT: {season_name} - directorio no encontrado")
            continue
        
        fbref_index = build_fbref_index(season_dir)
        process_understat_season(understat_dir, fbref_index, season_name)
    
    print("\nCompletado!")

if __name__ == "__main__":
    main()