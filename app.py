import streamlit as st
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==============================================================================
# 1. PAGE CONFIGURATION & CONSTANTS
# ==============================================================================
st.set_page_config(
    page_title="Pro +EV Terminal (Omni-Market)",
    page_icon="🔥",
    layout="wide"
)

# 1. Your actual funded sportsbooks
MD_BOOKS = ["draftkings", "fanduel", "espnbet"]

# 2. Strict Sharps for Main Lines (Moneylines, Spreads, Totals)
SHARP_BOOKS_MAIN = ["pinnacle", "circasports"]

# 3. Necessary Offshore Sharps for Player Props
SHARP_BOOKS_PROPS = ["bovada", "betonlineag"]

# THE OMNI-MARKET DICTIONARY
PROP_MARKETS = {
    "baseball_mlb": (
        "batter_home_runs,batter_hits,batter_total_bases,batter_rbis,batter_runs_scored,"
        "batter_hits_runs_rbis,batter_singles,batter_doubles,batter_triples,batter_walks,"
        "batter_strikeouts,batter_stolen_bases,pitcher_strikeouts,pitcher_hits_allowed,"
        "pitcher_walks,pitcher_earned_runs,pitcher_outs,"
        "totals_1st_1_innings,h2h_1st_5_innings,spreads_1st_5_innings,totals_1st_5_innings"
    ),
    "basketball_nba": (
        "player_points,player_rebounds,player_assists,player_threes,player_blocks,player_steals,"
        "player_turnovers,player_points_rebounds_assists,player_points_rebounds,"
        "player_points_assists,player_rebounds_assists,"
        "h2h_q1,h2h_q2,h2h_q3,h2h_q4,h2h_h1,h2h_h2,"
        "spreads_q1,spreads_h1,totals_q1,totals_h1"
    ),
    "mma_mixed_martial_arts": "method_of_victory,round_betting",
    "tennis": "h2h_s1,spreads_s1"
}

# ==============================================================================
# 2. HELPER CALCULATIONS
# ==============================================================================
def american_to_decimal(american):
    if american > 0:
        return (american / 100.0) + 1.0
    else:
        return (100.0 / abs(american)) + 1.0

def decimal_to_american(dec):
    if dec >= 2.0:
        return int(round((dec - 1.0) * 100))
    elif dec > 1.0:
        return int(round(-100 / (dec - 1.0)))
    return 0

def devig_power(implied_a, implied_b):
    total_implied = implied_a + implied_b
    if total_implied <= 1.0:
        return implied_a, implied_b
    low, high = 1.0, 20.0
    for _ in range(50):
        mid = (low + high) / 2.0
        val = (implied_a ** mid) + (implied_b ** mid)
        if val > 1.0:
            low = mid
        else:
            high = mid
    k = (low + high) / 2.0
    return implied_a ** k, implied_b ** k

def calculate_ev(fair_prob, target_odds_american):
    target_dec = american_to_decimal(target_odds_american)
    return ((fair_prob * target_dec) - 1.0) * 100.0

def calculate_kelly(fair_prob, target_odds_american, fraction, bankroll):
    b = american_to_decimal(target_odds_american) - 1.0
    q = 1.0 - fair_prob
    if b <= 0: return 0.0
    f_star = (b * fair_prob - q) / b
    return max(0.0, round(f_star * fraction * bankroll, 2))

@st.cache_data(ttl=60)
def get_active_tennis_tournaments(api_key):
    try:
        res = requests.get("https://api.the-odds-api.com/v4/sports", params={"apiKey": api_key}, timeout=5)
        if res.status_code == 200:
            return [sport['key'] for sport in res.json() if 'tennis' in sport.get('key', '')]
    except: pass
    return []

# ==============================================================================
# 3. PARALLEL API WORKERS (WITH ERROR LOGGING)
# ==============================================================================
def fetch_odds_worker(sport, markets, api_key, session):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {'apiKey': api_key, 'regions': 'us,us2,eu', 'markets': markets, 'oddsFormat': 'american'}
    try:
        res = session.get(url, params=params, timeout=5)
        if res.status_code == 200:
            return sport, res.json(), res.headers.get('x-requests-remaining')
        else:
            print(f"[API ERROR - MAIN LINES] Sport: {sport} | Code: {res.status_code} | Msg: {res.text}")
    except Exception as e: 
        print(f"[FETCH ERROR] {e}")
    return sport, None, None

def fetch_events_worker(sport, api_key, session):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/events"
    params = {'apiKey': api_key}
    try:
        res = session.get(url, params=params, timeout=5)
        if res.status_code == 200:
            return sport, res.json(), res.headers.get('x-requests-remaining')
        else:
            print(f"[API ERROR - EVENTS] Sport: {sport} | Code: {res.status_code} | Msg: {res.text}")
    except Exception as e: 
        print(f"[FETCH ERROR] {e}")
    return sport, [], None

def fetch_props_worker(sport, event_id, prop_markets, api_key, session):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/events/{event_id}/odds/"
    params = {'apiKey': api_key, 'regions': 'us,us2,eu', 'markets': prop_markets, 'oddsFormat': 'american'}
    try:
        res = session.get(url, params=params, timeout=5)
        if res.status_code == 200:
            return sport, [res.json()], res.headers.get('x-requests-remaining')
        else:
            print(f"[API ERROR - PROPS] Event: {event_id} | Code: {res.status_code} | Msg: {res.text}")
    except Exception as e: 
        print(f"[FETCH ERROR] {e}")
    return sport, None, None

# ==============================================================================
# 4. UI SIDEBAR CONTROLS
# ==============================================================================
st.sidebar.title("Omni-Market Settings")
api_key = st.sidebar.text_input("The Odds API Key", type="password")

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 Scan Modules")
scan_main = st.sidebar.checkbox("Main Lines (ML, Spreads, Totals)", value=True)
scan_props = st.sidebar.checkbox("Props, Exotics & Halves", value=True)

st.sidebar.markdown("---")
st.sidebar.subheader("💰 Bankroll & Risk")
bankroll = st.sidebar.number_input("Total Bankroll ($)", min_value=10.0, value=1000.0, step=100.0)
kelly_fraction = st.sidebar.slider("Kelly Multiplier", 0.1, 1.0, 0.25, 0.05)

# THE NEW FILTERS:
ev_range = st.sidebar.slider("Target EV Range (%)", min_value=0.0, max_value=10.0, value=(2.0, 3.0), step=0.1)
max_sharp_hold = st.sidebar.slider("Max Sharp Hold (%)", min_value=1.0, max_value=15.0, value=7.5, step=0.5)

st.sidebar.markdown("---")
st.sidebar.subheader("📍 Location Setup")
md_filter = st.sidebar.checkbox("Show ONLY My Funded Books", value=True)

st.sidebar.markdown("---")
selected_sports = st.sidebar.multiselect(
    "Select Sports",
    options=["baseball_mlb", "basketball_nba", "mma_mixed_martial_arts", "tennis"],
    default=["baseball_mlb", "basketball_nba", "mma_mixed_martial_arts", "tennis"]
)

# ==============================================================================
# 5. EXECUTION & LOGIC
# ==============================================================================
st.title("🔥 Omni-Market Consensus Scanner")

if st.button("⚡ Execute Deep Scan", type="primary", use_container_width=True):
    if not api_key:
        st.error("API Key required.")
    elif not scan_main and not scan_props:
        st.warning("Select at least one market type to scan.")
    else:
        with st.spinner("Executing Deep Data Pull across all markets..."):
            
            sports_to_scan = []
            for sport in selected_sports:
                if sport == "tennis":
                    sports_to_scan.extend(get_active_tennis_tournaments(api_key))
                else: sports_to_scan.append(sport)

            ev_opportunities = []
            req_remaining = None
            event_ids_by_sport = {s: [] for s in sports_to_scan}
            
            session = requests.Session()
            raw_results = []
            
            # --- PHASE 1: Main Lines ---
            if scan_main:
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [executor.submit(fetch_odds_worker, sport, "h2h,spreads,totals", api_key, session) for sport in sports_to_scan]
                    for future in as_completed(futures):
                        sport, data, remaining = future.result()
                        if data:
                            raw_results.append((sport, data))
                            for event in data:
                                if event['id'] not in event_ids_by_sport[sport]:
                                    event_ids_by_sport[sport].append(event['id'])
                        if remaining: req_remaining = remaining

            # --- PHASE 2: Props & Exotics ---
            if scan_props:
                if not scan_main:
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        futures = [executor.submit(fetch_events_worker, sport, api_key, session) for sport in sports_to_scan]
                        for future in as_completed(futures):
                            sport, events_data, remaining = future.result()
                            if events_data:
                                for event in events_data:
                                    event_ids_by_sport[sport].append(event['id'])
                            if remaining: req_remaining = remaining

                prop_futures = []
                with ThreadPoolExecutor(max_workers=15) as executor:
                    for sport, e_ids in event_ids_by_sport.items():
                        
                        # THE TENNIS FIX
                        if "tennis" in sport:
                            p_markets = PROP_MARKETS.get("tennis", "")
                        else:
                            p_markets = PROP_MARKETS.get(sport, "")
                            
                        if p_markets:
                            for e_id in e_ids:
                                prop_futures.append(executor.submit(fetch_props_worker, sport, e_id, p_markets, api_key, session))
                    
                    for future in as_completed(prop_futures):
                        sport, data, remaining = future.result()
                        if data:
                            raw_results.append((sport, data))
                        if remaining: req_remaining = remaining

            # --- PHASE 3: Universal Devig Engine ---
            for sport, data in raw_results:
                for event in data:
                    matchup = f"{event.get('away_team')} @ {event.get('home_team')}"
                    bookies = {b['key']: b for b in event.get('bookmakers', [])}
                    
                    true_probs_accum = {}
                    sharp_holds = {}
                    
                    # 3A. Dynamic Sharp Consensus
                    for book_key, book in bookies.items():
                        for market in book.get('markets', []):
                            m_key = market['key']
                            is_main_line = m_key in ['h2h', 'spreads', 'totals']
                            active_sharps = SHARP_BOOKS_MAIN if is_main_line else SHARP_BOOKS_PROPS
                            
                            if book_key not in active_sharps: 
                                continue
                            
                            groups = {}
                            for out in market['outcomes']:
                                desc = out.get('description', 'Game')
                                pt = out.get('point')
                                g_key = f"{m_key}_{desc}_{abs(pt) if pt is not None else 'None'}"
                                if g_key not in groups: groups[g_key] = []
                                groups[g_key].append(out)
                            
                            for g_key, outs in groups.items():
                                if len(outs) == 2:
                                    try:
                                        implied_a = 1.0 / american_to_decimal(outs[0]['price'])
                                        implied_b = 1.0 / american_to_decimal(outs[1]['price'])
                                    except: continue
                                        
                                    market_hold_pct = (implied_a + implied_b - 1.0) * 100
                                    fair_a, fair_b = devig_power(implied_a, implied_b)
                                    
                                    b_key_a = (m_key, outs[0]['name'], outs[0].get('description', 'Game'), outs[0].get('point'))
                                    b_key_b = (m_key, outs[1]['name'], outs[1].get('description', 'Game'), outs[1].get('point'))
                                    
                                    if b_key_a not in true_probs_accum: true_probs_accum[b_key_a] = []
                                    if b_key_b not in true_probs_accum: true_probs_accum[b_key_b] = []
                                        
                                    true_probs_accum[b_key_a].append(fair_a)
                                    true_probs_accum[b_key_b].append(fair_b)
                                    sharp_holds[b_key_a] = market_hold_pct
                                    sharp_holds[b_key_b] = market_hold_pct
                                    
                    if not true_probs_accum: continue
                    true_probs = {k: sum(v)/len(v) for k, v in true_probs_accum.items()}
                    
                    # 3B. Soft Book Hunting
                    for book_key, book in bookies.items():
                        if md_filter and book_key not in MD_BOOKS: 
                            continue
                            
                        for market in book.get('markets', []):
                            m_key = market['key']
                            is_main_line = m_key in ['h2h', 'spreads', 'totals']
                            active_sharps = SHARP_BOOKS_MAIN if is_main_line else SHARP_BOOKS_PROPS
                            
                            if book_key in active_sharps: 
                                continue
                                
                            for out in market['outcomes']:
                                bet_key = (m_key, out['name'], out.get('description', 'Game'), out.get('point'))
                                
                                if bet_key in true_probs:
                                    true_p = true_probs[bet_key]
                                    soft_odds = out['price']
                                    ev_pct = calculate_ev(true_p, soft_odds)
                                    hold_pct = sharp_holds.get(bet_key, 0.0)
                                    
                                    # THE FIX: Now using the adjustable max_sharp_hold
                                    if (ev_range[0] <= ev_pct <= ev_range[1]) and (hold_pct <= max_sharp_hold):
                                        stake = calculate_kelly(true_p, soft_odds, kelly_fraction, bankroll)
                                        no_vig_american = decimal_to_american(1.0 / true_p)
                                        
                                        market_display = m_key.replace('_', ' ').title()
                                        selection_str = out['name']
                                        if out.get('description') and out.get('description') != 'Game':
                                            selection_str = f"{out['description']} {selection_str}"
                                        if out.get('point') is not None:
                                            pt = out['point']
                                            pt_str = f"+{pt}" if pt > 0 and 'spread' in m_key else str(pt)
                                            selection_str += f" ({pt_str})"
                                            
                                        ev_opportunities.append({
                                            "Sport": sport.upper().replace("_", " "),
                                            "Matchup": matchup,
                                            "Market": market_display,
                                            "Selection": selection_str,
                                            "Soft Book": book['title'],
                                            "Odds": f"{soft_odds:+d}" if soft_odds > 0 else str(soft_odds),
                                            "Fair Odds": f"{no_vig_american:+d}" if no_vig_american > 0 else str(no_vig_american),
                                            "Win %": f"{true_p * 100:.1f}%",
                                            "Edge": ev_pct,
                                            "Sharp Hold": hold_pct,
                                            "Rec Stake": f"${stake:.2f}"
                                        })

            # --- RENDER DATAFRAME ---
            if req_remaining is not None:
                st.caption(f"Diagnostics: Engine finished. {req_remaining} API credits remaining.")

            if ev_opportunities:
                df = pd.DataFrame(ev_opportunities).drop_duplicates()
                df = df.sort_values(by="Edge", ascending=False)
                
                formatted_df = df.copy()
                formatted_df['Edge'] = formatted_df['Edge'].apply(lambda x: f"{x:.2f}%")
                formatted_df['Sharp Hold'] = formatted_df['Sharp Hold'].apply(lambda x: f"{x:.2f}%")
                
                st.success(f"Found {len(df)} sweet-spot plays ({ev_range[0]}%–{ev_range[1]}% EV & Sharp Hold ≤ {max_sharp_hold}%).")
                st.dataframe(formatted_df, use_container_width=True, hide_index=True)
            else:
                st.warning("No plays found meeting your sweet-spot criteria right now.")
