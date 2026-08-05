import streamlit as st
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

# ==============================================================================
# 1. PAGE CONFIGURATION & CONSTANTS
# ==============================================================================
st.set_page_config(
    page_title="OMEGA God Mode Sniper (Props & Halves)",
    page_icon="🎯",
    layout="wide"
)

MD_BOOKS = ["draftkings", "fanduel", "espnbet", "betmgm", "caesars"]
SHARP_BOOKS_PROPS = ["bovada", "betonlineag", "pinnacle"]

# Focused STRICTLY on MLB, NBA, NFL, and UFC Props, Exotics, and Halves
PROP_MARKETS = {
    "baseball_mlb": "batter_home_runs,batter_strikeouts,pitcher_strikeouts,h2h_1st_5_innings,spreads_1st_5_innings,totals_1st_5_innings",
    "basketball_nba": "player_points,player_rebounds,player_assists,player_threes,h2h_q1,h2h_h1,spreads_h1,totals_h1",
    "american_football_nfl": "player_pass_tds,player_pass_yds,player_rush_yds,player_receptions,player_reception_yds,player_anytime_td,h2h_h1,spreads_h1,totals_h1",
    "mma_mixed_martial_arts": "method_of_victory,round_betting"
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

# The Power Devig method is mathematically optimal for props to remove the favorite-longshot bias
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

# ==============================================================================
# 3. TIER CLASSIFICATION & STYLING
# ==============================================================================
def get_tier(ev, hold):
    # OMEGA: Insane value (EV >= 4.5%) combined with extreme sharp confidence (Hold <= 5.5%)
    if hold <= 5.5 and ev >= 4.5:
        return '🟢 OMEGA TIER'
    # ELITE: Strong value (EV >= 3.0%) with highly confident sharps (Hold <= 6.5%)
    elif hold <= 6.5 and ev >= 3.0:
        return '🟡 ELITE TIER'
    # VALUE: Minimum acceptable threshold for taking a prop/half
    elif hold <= 7.0 and ev >= 2.0:
        return '🔵 VALUE TIER'
    return None # Trash plays return None and get filtered out

def style_dataframe(df):
    def highlight_rows(row):
        if row['Tier'] == '🟢 OMEGA TIER':
            return ['background-color: rgba(0, 255, 0, 0.15)'] * len(row)
        elif row['Tier'] == '🟡 ELITE TIER':
            return ['background-color: rgba(255, 215, 0, 0.15)'] * len(row)
        elif row['Tier'] == '🔵 VALUE TIER':
            return ['background-color: rgba(0, 191, 255, 0.15)'] * len(row)
        return [''] * len(row)
    return df.style.apply(highlight_rows, axis=1)

# ==============================================================================
# 4. PARALLEL API WORKERS 
# ==============================================================================
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
    # Strictly US region to save API credits and speed up execution
    params = {'apiKey': api_key, 'regions': 'us', 'markets': prop_markets, 'oddsFormat': 'american'}
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
# 5. UI SIDEBAR CONTROLS
# ==============================================================================
st.sidebar.title("🎯 God Mode Settings")

# API key locked in by default
api_key = st.sidebar.text_input(
    "The Odds API Key", 
    value="59331ea391b20784a92c2682c3f4b1f6", 
    type="password"
)

st.sidebar.markdown("---")
st.sidebar.subheader("💰 Bankroll & Risk")
bankroll = st.sidebar.number_input("Total Bankroll ($)", min_value=10.0, value=1000.0, step=100.0)
kelly_fraction = st.sidebar.slider("Kelly Multiplier (Keep it low for variance)", 0.1, 1.0, 0.25, 0.05)

st.sidebar.markdown("---")
st.sidebar.subheader("📍 Location Setup")
md_filter = st.sidebar.checkbox("Show ONLY My Funded Books", value=True)

st.sidebar.markdown("---")
selected_sports = st.sidebar.multiselect(
    "Select Sports",
    options=["baseball_mlb", "basketball_nba", "american_football_nfl", "mma_mixed_martial_arts"],
    default=["baseball_mlb", "american_football_nfl", "mma_mixed_martial_arts"] 
)

# ==============================================================================
# 6. EXECUTION & LOGIC
# ==============================================================================
st.title("🎯 OMEGA Tier Sniper (Strict Pre-Game Props & Halves)")
st.markdown("This model strictly filters out the noise and **blocks live games**. If the sharp books are guessing, or if the game has already started, we don't bet.")

if st.button("⚡ EXECUTE GOD MODE SCAN", type="primary", use_container_width=True):
    if not api_key:
        st.error("API Key required.")
    else:
        with st.spinner("Locking on to strict value props..."):
            
            sports_to_scan = selected_sports
            ev_opportunities = []
            req_remaining = None
            event_ids_by_sport = {s: [] for s in sports_to_scan}
            
            session = requests.Session()
            raw_results = []
            
            # PHASE 1: GET EVENTS
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(fetch_events_worker, sport, api_key, session) for sport in sports_to_scan]
                for future in as_completed(futures):
                    sport, events_data, remaining = future.result()
                    if events_data:
                        for event in events_data:
                            event_ids_by_sport[sport].append(event['id'])
                    if remaining: req_remaining = remaining

            # PHASE 2: GET PROPS & HALVES
            prop_futures = []
            with ThreadPoolExecutor(max_workers=15) as executor:
                for sport, e_ids in event_ids_by_sport.items():
                    p_markets = PROP_MARKETS.get(sport, "")
                        
                    if p_markets:
                        for e_id in e_ids:
                            prop_futures.append(executor.submit(fetch_props_worker, sport, e_id, p_markets, api_key, session))
                
                for future in as_completed(prop_futures):
                    sport, data, remaining = future.result()
                    if data:
                        raw_results.append((sport, data))
                    if remaining: req_remaining = remaining

            # PHASE 3: THE SNIPER ENGINE
            for sport, data in raw_results:
                for event in data:
                    
                    # ==========================================
                    # 🛑 THE LIVE GAME KILLSWITCH 🛑
                    # ==========================================
                    commence_time = event.get('commence_time')
                    if commence_time:
                        game_start = datetime.strptime(commence_time, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        # If the game start time is in the past, skip it entirely
                        if game_start < datetime.now(timezone.utc):
                            continue
                    # ==========================================

                    matchup = f"{event.get('away_team')} @ {event.get('home_team')}"
                    bookies = {b['key']: b for b in event.get('bookmakers', [])}
                    
                    true_probs_accum = {}
                    sharp_holds = {}
                    
                    # 3A. Extract Sharp Baselines
                    for book_key, book in bookies.items():
                        if book_key not in SHARP_BOOKS_PROPS: 
                            continue
                            
                        for market in book.get('markets', []):
                            m_key = market['key']
                            
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
                    
                    # 3B. Hunt for God Tier Value
                    for book_key, book in bookies.items():
                        if md_filter and book_key not in MD_BOOKS: 
                            continue
                        if book_key in SHARP_BOOKS_PROPS: 
                            continue
                                
                        for market in book.get('markets', []):
                            m_key = market['key']
                                
                            for out in market['outcomes']:
                                bet_key = (m_key, out['name'], out.get('description', 'Game'), out.get('point'))
                                
                                if bet_key in true_probs:
                                    true_p = true_probs[bet_key]
                                    soft_odds = out['price']
                                    ev_pct = calculate_ev(true_p, soft_odds)
                                    hold_pct = sharp_holds.get(bet_key, 100.0)
                                    
                                    # STRICT TIER SYSTEM FILTER
                                    tier = get_tier(ev_pct, hold_pct)
                                    if tier:
                                        stake = calculate_kelly(true_p, soft_odds, kelly_fraction, bankroll)
                                        
                                        market_display = m_key.replace('_', ' ').title()
                                        selection_str = out['name']
                                        if out.get('description') and out.get('description') != 'Game':
                                            selection_str = f"{out['description']} {selection_str}"
                                        if out.get('point') is not None:
                                            pt = out['point']
                                            pt_str = f"+{pt}" if pt > 0 and 'spread' in m_key else str(pt)
                                            selection_str += f" ({pt_str})"
                                            
                                        ev_opportunities.append({
                                            "Tier": tier,
                                            "Matchup": matchup,
                                            "Market": market_display,
                                            "Selection": selection_str,
                                            "Soft Book": book['title'].upper(),
                                            "Odds": f"{soft_odds:+d}" if soft_odds > 0 else str(soft_odds),
                                            "Edge": ev_pct,
                                            "Sharp Hold": hold_pct,
                                            "Rec Stake": f"${stake:.2f}"
                                        })

            # --- RENDER OMEGA DATAFRAME ---
            if req_remaining is not None:
                st.caption(f"Diagnostics: Engine finished. {req_remaining} API credits remaining.")

            if ev_opportunities:
                df = pd.DataFrame(ev_opportunities).drop_duplicates()
                
                tier_order = {'🟢 OMEGA TIER': 0, '🟡 ELITE TIER': 1, '🔵 VALUE TIER': 2}
                df['TierRank'] = df['Tier'].map(tier_order)
                df = df.sort_values(by=["TierRank", "Edge"], ascending=[True, False]).drop(columns=['TierRank'])
                
                df['Edge'] = df['Edge'].apply(lambda x: f"{x:.2f}%")
                df['Sharp Hold'] = df['Sharp Hold'].apply(lambda x: f"{x:.2f}%")
                
                st.success(f"Sniper locked on. Found {len(df)} heavily vetted pre-game plays.")
                
                st.dataframe(style_dataframe(df), use_container_width=True, hide_index=True)
            else:
                st.error("No God Tier or Elite PRE-GAME plays currently available. The books are tight right now. Save your money and scan later.")
