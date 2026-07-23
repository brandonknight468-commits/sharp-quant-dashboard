import streamlit as st
import requests
import pandas as pd

# ==============================================================================
# 1. PAGE CONFIGURATION
# ==============================================================================
st.set_page_config(
    page_title="+EV Sports Betting Scanner",
    page_icon="⚡",
    layout="wide"
)

# ==============================================================================
# 2. HELPER CALCULATIONS & FUNCTIONS
# ==============================================================================
def american_to_decimal(american):
    """Converts American odds (e.g. +150, -110) to Decimal odds."""
    if american > 0:
        return (american / 100.0) + 1.0
    else:
        return (100.0 / abs(american)) + 1.0

def calculate_ev(devigged_prob, target_odds_american):
    """Calculates Expected Value percentage (+EV%)."""
    target_dec = american_to_decimal(target_odds_american)
    profit = target_dec - 1.0
    loss_prob = 1.0 - devigged_prob
    ev = (devigged_prob * profit) - loss_prob
    return ev * 100.0

def calculate_kelly(devigged_prob, target_odds_american, fraction=0.25, bankroll=1000):
    """Calculates Fractional Kelly bet sizing in dollars ($)."""
    b = american_to_decimal(target_odds_american) - 1.0
    p = devigged_prob
    q = 1.0 - p
    f_star = (b * p - q) / b
    if f_star <= 0:
        return 0.0
    return round(f_star * fraction * bankroll, 2)

def devig_multiplicative(sharp_odds_dict):
    """Strips vig from sharp bookmaker odds using the multiplicative method."""
    if len(sharp_odds_dict) < 2:
        return None
    
    implied_probs = {}
    total_implied = 0.0
    for name, odds in sharp_odds_dict.items():
        dec = american_to_decimal(odds)
        prob = 1.0 / dec
        implied_probs[name] = prob
        total_implied += prob
    
    # Normalize back to 100% fair probability
    return {name: prob / total_implied for name, prob in implied_probs.items()}

def get_active_tennis_tournaments(api_key):
    """Fetches currently active tennis keys dynamically for 0 API credits."""
    url = "https://api.the-odds-api.com/v4/sports"
    try:
        response = requests.get(url, params={"apiKey": api_key}, timeout=10)
        if response.status_code == 200:
            return [sport['key'] for sport in response.json() if 'tennis' in sport.get('key', '')]
    except Exception:
        pass
    return []

# ==============================================================================
# 3. SIDEBAR CONTROLS
# ==============================================================================
st.sidebar.title("⚙️ Scanner Settings")

api_key = st.sidebar.text_input("The Odds API Key", type="password")

bankroll = st.sidebar.number_input("Total Bankroll ($)", min_value=10.0, value=1000.0, step=50.0)
min_ev = st.sidebar.slider("Minimum EV Threshold (%)", min_value=0.5, max_value=15.0, value=2.0, step=0.5)

selected_sports = st.sidebar.multiselect(
    "Select Sports",
    options=["baseball_mlb", "basketball_nba", "mma_mixed_martial_arts", "tennis"],
    default=["baseball_mlb", "basketball_nba", "mma_mixed_martial_arts", "tennis"],
    format_func=lambda x: {
        "baseball_mlb": "⚾ MLB",
        "basketball_nba": "🏀 NBA",
        "mma_mixed_martial_arts": "🥊 UFC / MMA",
        "tennis": "🎾 Tennis (All Active Tournaments)"
    }.get(x, x)
)

sharp_books = st.sidebar.multiselect(
    "Sharp Books (for devigging)",
    options=["pinnacle", "bookmaker", "circasports", "betonlineag"],
    default=["pinnacle", "bookmaker"]
)

# ==============================================================================
# 4. MAIN INTERFACE & LOGIC
# ==============================================================================
st.title("⚡ Real-Time +EV Odds Scanner")
st.markdown("Find mathematically profitable bets by devigging sharp bookmaker lines.")

if st.button("🚀 Scan Markets for +EV Bets", type="primary"):
    if not api_key:
        st.error("Please enter your API Key from The Odds API in the sidebar.")
    else:
        with st.spinner("Scanning active markets and stripping vig..."):
            
            # 1. Expand "tennis" into specific active tournament keys dynamically
            sports_to_scan = []
            for sport in selected_sports:
                if sport == "tennis":
                    active_tennis = get_active_tennis_tournaments(api_key)
                    if not active_tennis:
                        st.sidebar.warning("🎾 No active tennis tournaments found right now.")
                    sports_to_scan.extend(active_tennis)
                else:
                    sports_to_scan.append(sport)

            ev_opportunities = []
            requests_remaining = None
            requests_used = None

            # 2. Iterate through resolved sports
            for sport in sports_to_scan:
                url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
                params = {
                    'apiKey': api_key,
                    'regions': 'us,eu',
                    'markets': 'h2h',
                    'oddsFormat': 'american'
                }
                
                try:
                    res = requests.get(url, params=params, timeout=10)
                    
                    # Track API usage from response headers
                    if 'x-requests-remaining' in res.headers:
                        requests_remaining = res.headers['x-requests-remaining']
                        requests_used = res.headers['x-requests-used']

                    if res.status_code != 200:
                        st.warning(f"Could not fetch {sport}: {res.json().get('message', 'API Error')}")
                        continue
                        
                    data = res.json()
                    
                    for event in data:
                        event_title = f"{event.get('away_team', 'TBD')} @ {event.get('home_team', 'TBD')}"
                        commence_time = event.get('commence_time', '')[:16].replace('T', ' ')
                        
                        # Gather sharp odds
                        sharp_lines = {}
                        bookmaker_data = {b['key']: b for b in event.get('bookmakers', [])}
                        
                        for sharp in sharp_books:
                            if sharp in bookmaker_data:
                                for market in bookmaker_data[sharp].get('markets', []):
                                    if market['key'] == 'h2h':
                                        for outcome in market['outcomes']:
                                            name = outcome['name']
                                            price = outcome['price']
                                            if name not in sharp_lines:
                                                sharp_lines[name] = []
                                            sharp_lines[name].append(price)

                        # Average sharp lines if multiple sharp books are available
                        avg_sharp_odds = {}
                        for outcome_name, odds_list in sharp_lines.items():
                            avg_sharp_odds[outcome_name] = sum(odds_list) / len(odds_list)
                            
                        fair_probs = devig_multiplicative(avg_sharp_odds)
                        if not fair_probs:
                            continue

                        # Compare soft bookmakers against devigged fair probabilities
                        for book_key, book in bookmaker_data.items():
                            if book_key in sharp_books:
                                continue  # Skip soft analysis on selected sharp books
                                
                            for market in book.get('markets', []):
                                if market['key'] == 'h2h':
                                    for outcome in market['outcomes']:
                                        outcome_name = outcome['name']
                                        target_odds = outcome['price']
                                        
                                        if outcome_name in fair_probs:
                                            fair_p = fair_probs[outcome_name]
                                            ev_val = calculate_ev(fair_p, target_odds)
                                            
                                            if ev_val >= min_ev:
                                                recommended_stake = calculate_kelly(fair_p, target_odds, bankroll=bankroll)
                                                
                                                ev_opportunities.append({
                                                    "Sport": sport.upper(),
                                                    "Matchup": event_title,
                                                    "Selection": outcome_name,
                                                    "Soft Book": book['title'],
                                                    "Offered Odds": f"{target_odds:+d}" if target_odds > 0 else str(target_odds),
                                                    "Fair Odds": f"{int(round((1/(fair_p-1))*100)):+d}" if fair_p < 0.5 else f"+{int(round((fair_p/(1-fair_p))*100))}",
                                                    "Fair Win %": f"{fair_p * 100:.1f}%",
                                                    "+EV %": f"{ev_val:.2f}%",
                                                    "Kelly Bet ($)": f"${recommended_stake:.2f}",
                                                    "Start Time": commence_time
                                                })

                except Exception as e:
                    st.error(f"Error processing {sport}: {e}")

            # 3. Display Quota Header
            if requests_remaining is not None:
                st.info(f"📊 **API Quota Used:** {requests_used} | **Credits Remaining:** {requests_remaining}")

            # 4. Display Results Table
            if ev_opportunities:
                st.success(f"🎯 Found **{len(ev_opportunities)}** positive EV bet(s)!")
                df = pd.DataFrame(ev_opportunities)
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("No +EV opportunities found meeting your current criteria. Try lowering the Minimum EV slider or selecting more sports.")
