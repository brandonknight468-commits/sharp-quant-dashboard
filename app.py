import streamlit as st
import requests
import pandas as pd
import time

# ==============================================================================
# 1. PAGE CONFIGURATION
# ==============================================================================
st.set_page_config(
    page_title="Pro +EV Odds Terminal",
    page_icon="📈",
    layout="wide"
)

# ==============================================================================
# 2. HELPER CALCULATIONS & DEVIGGING MATH
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

def devig_lines(implied_a, implied_b, method="Multiplicative"):
    """Strips vig using either Multiplicative (Proportional) or Additive (Margin) methods."""
    total_implied = implied_a + implied_b
    if total_implied <= 1.0:
        return implied_a, implied_b # No vig to strip
        
    if method == "Multiplicative":
        return implied_a / total_implied, implied_b / total_implied
    elif method == "Additive":
        margin_per_side = (total_implied - 1.0) / 2.0
        return implied_a - margin_per_side, implied_b - margin_per_side
    
    return implied_a, implied_b

def calculate_ev(fair_prob, target_odds_american):
    target_dec = american_to_decimal(target_odds_american)
    return ((fair_prob * target_dec) - 1.0) * 100.0

def calculate_kelly(fair_prob, target_odds_american, fraction, bankroll):
    b = american_to_decimal(target_odds_american) - 1.0
    q = 1.0 - fair_prob
    if b <= 0: return 0.0
    f_star = (b * fair_prob - q) / b
    return max(0.0, round(f_star * fraction * bankroll, 2))

@st.cache_data(ttl=60) # Caches data for 60 seconds to save API credits
def get_active_tennis_tournaments(api_key):
    try:
        res = requests.get("https://api.the-odds-api.com/v4/sports", params={"apiKey": api_key}, timeout=10)
        if res.status_code == 200:
            return [sport['key'] for sport in res.json() if 'tennis' in sport.get('key', '')]
    except: pass
    return []

# ==============================================================================
# 3. SIDEBAR CONTROLS (THE TERMINAL)
# ==============================================================================
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/e/e4/Function-graph.svg/1024px-Function-graph.svg.png", width=50)
st.sidebar.title("Terminal Settings")

api_key = st.sidebar.text_input("The Odds API Key", type="password")

st.sidebar.markdown("---")
st.sidebar.subheader("💰 Bankroll & Risk")
bankroll = st.sidebar.number_input("Total Bankroll ($)", min_value=10.0, value=1000.0, step=100.0)
kelly_fraction = st.sidebar.slider("Kelly Multiplier", 0.1, 1.0, 0.25, 0.05, help="0.25 = Quarter Kelly (Recommended)")
min_ev = st.sidebar.slider("Min EV Edge (%)", 0.0, 10.0, 1.5, 0.1)

st.sidebar.markdown("---")
st.sidebar.subheader("📐 Model Parameters")
devig_method = st.sidebar.selectbox("Devigging Method", ["Multiplicative", "Additive"])

# Define the sharp bookmakers to build the Consensus Line
SHARP_BOOKS = ["pinnacle", "bookmaker", "circasports", "betonlineag"]

selected_sports = st.sidebar.multiselect(
    "Select Sports to Scan",
    options=["baseball_mlb", "basketball_nba", "mma_mixed_martial_arts", "tennis"],
    default=["baseball_mlb", "mma_mixed_martial_arts"]
)

# ==============================================================================
# 4. MAIN INTERFACE & SCAN LOGIC
# ==============================================================================
st.title("📈 Consensus Sharp Market Scanner")
st.markdown(f"**Devigging Engine:** `{devig_method}` | **Consensus Base:** `Pinnacle, Circa, Bookmaker, BetOnline`")

if st.button("⚡ Execute Market Scan", type="primary", use_container_width=True):
    if not api_key:
        st.error("API Key required. Please input in the sidebar.")
    else:
        with st.spinner("Compiling Consensus Sharp Lines..."):
            
            # Resolve Tennis
            sports_to_scan = []
            for sport in selected_sports:
                if sport == "tennis":
                    sports_to_scan.extend(get_active_tennis_tournaments(api_key))
                else:
                    sports_to_scan.append(sport)

            ev_opportunities = []
            req_remaining, req_used = None, None

            for sport in sports_to_scan:
                url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
                params = {'apiKey': api_key, 'regions': 'us,eu', 'markets': 'h2h', 'oddsFormat': 'american'}
                
                try:
                    res = requests.get(url, params=params, timeout=10)
                    if 'x-requests-remaining' in res.headers:
                        req_remaining = res.headers['x-requests-remaining']
                        req_used = res.headers['x-requests-used']

                    if res.status_code != 200: continue
                    data = res.json()
                    
                    for event in data:
                        matchup = f"{event.get('away_team')} @ {event.get('home_team')}"
                        bookies = {b['key']: b for b in event.get('bookmakers', [])}
                        
                        # 1. BUILD THE CONSENSUS SHARP LINE
                        sharp_implied = {}
                        for sharp in SHARP_BOOKS:
                            if sharp in bookies:
                                for market in bookies[sharp].get('markets', []):
                                    if market['key'] == 'h2h' and len(market['outcomes']) == 2:
                                        for out in market['outcomes']:
                                            if out['name'] not in sharp_implied:
                                                sharp_implied[out['name']] = []
                                            # Convert American to Implied Prob
                                            sharp_implied[out['name']].append(1.0 / american_to_decimal(out['price']))

                        # Need exactly two outcomes and at least one sharp book to proceed
                        if len(sharp_implied) != 2: continue
                        
                        outcomes = list(sharp_implied.keys())
                        if not sharp_implied[outcomes[0]] or not sharp_implied[outcomes[1]]: continue

                        # Average the implied probabilities across all available sharp books
                        avg_implied_a = sum(sharp_implied[outcomes[0]]) / len(sharp_implied[outcomes[0]])
                        avg_implied_b = sum(sharp_implied[outcomes[1]]) / len(sharp_implied[outcomes[1]])
                        
                        # Calculate market hold (Vig)
                        market_hold_pct = (avg_implied_a + avg_implied_b - 1.0) * 100

                        # Devig using the selected model
                        fair_p_a, fair_p_b = devig_lines(avg_implied_a, avg_implied_b, devig_method)
                        fair_probs = {outcomes[0]: fair_p_a, outcomes[1]: fair_p_b}

                        # 2. HUNT FOR SOFT LINE DISCREPANCIES
                        for book_key, book in bookies.items():
                            if book_key in SHARP_BOOKS: continue # Don't bet on the sharps
                                
                            for market in book.get('markets', []):
                                if market['key'] == 'h2h':
                                    for out in market['outcomes']:
                                        team = out['name']
                                        soft_odds = out['price']
                                        
                                        if team in fair_probs:
                                            true_prob = fair_probs[team]
                                            ev_pct = calculate_ev(true_prob, soft_odds)
                                            
                                            if ev_pct >= min_ev:
                                                stake = calculate_kelly(true_prob, soft_odds, kelly_fraction, bankroll)
                                                no_vig_american = decimal_to_american(1.0 / true_prob)
                                                
                                                ev_opportunities.append({
                                                    "Sport": sport.upper().replace("_", " "),
                                                    "Matchup": matchup,
                                                    "Selection": team,
                                                    "Soft Book": book['title'],
                                                    "Soft Odds": f"{soft_odds:+d}" if soft_odds > 0 else str(soft_odds),
                                                    "No-Vig Fair Odds": f"{no_vig_american:+d}" if no_vig_american > 0 else str(no_vig_american),
                                                    "True Win %": f"{true_prob * 100:.1f}%",
                                                    "Sharp Hold": f"{market_hold_pct:.1f}%",
                                                    "+EV Edge": ev_pct,
                                                    "Rec Stake": f"${stake:.2f}"
                                                })

                except Exception as e:
                    st.error(f"Failed to scan {sport}: {e}")

            # ==============================================================================
            # 5. RENDER THE PROFESSIONAL DATAFRAME
            # ==============================================================================
            if req_remaining is not None:
                st.caption(f"**Diagnostics:** Scan completed. {req_remaining} API credits remaining.")

            if ev_opportunities:
                df = pd.DataFrame(ev_opportunities)
                df = df.sort_values(by="+EV Edge", ascending=False)
                
                # Format EV Edge column as percentage string for display
                formatted_df = df.copy()
                formatted_df['+EV Edge'] = formatted_df['+EV Edge'].apply(lambda x: f"{x:.2f}%")
                
                st.success(f"**{len(df)} positive EV opportunities found across global markets.**")
                st.dataframe(formatted_df, use_container_width=True, hide_index=True)
            else:
                st.warning("No edges found meeting the strict consensus criteria right now. The market is highly efficient.")
