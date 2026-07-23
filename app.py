import streamlit as st
import pandas as pd
import requests

# Set Page Config
st.set_page_config(
    page_title="Sharp Market +EV Scanner",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ Sharp Market +EV Betting Scanner")
st.markdown("Find positive expected value (+EV) bets across **MLB, NBA, UFC, and Tennis** by devigging sharp bookmaker odds.")

# ---------------------------------------------------------
# HELPER FUNCTIONS & DEVIGGING MATH
# ---------------------------------------------------------

def american_to_decimal(american_odds):
    """Converts American odds to Decimal odds."""
    if american_odds > 0:
        return (american_odds / 100.0) + 1.0
    else:
        return (100.0 / abs(american_odds)) + 1.0

def decimal_to_implied(decimal_odds):
    """Calculates implied probability from decimal odds."""
    return 1.0 / decimal_odds

def devig_multiplicative(implied_a, implied_b):
    """
    Strips vigorish (house edge) using the Multiplicative method.
    Returns fair true probabilities for both sides.
    """
    total_implied = implied_a + implied_b
    fair_prob_a = implied_a / total_implied
    fair_prob_b = implied_b / total_implied
    return fair_prob_a, fair_prob_b

def calculate_ev(fair_prob, decimal_odds):
    """Calculates Expected Value percentage (+EV%)."""
    return (fair_prob * decimal_odds) - 1.0

def calculate_kelly(fair_prob, decimal_odds, fraction=0.25):
    """Calculates Fractional Kelly Criterion stake recommendation."""
    b = decimal_odds - 1.0
    q = 1.0 - fair_prob
    if b <= 0:
        return 0.0
    kelly = (b * fair_prob - q) / b
    return max(0.0, kelly * fraction)

# ---------------------------------------------------------
# SIDEBAR CONTROLS
# ---------------------------------------------------------
st.sidebar.header("⚙️ Scanner Settings")

# Check for API key in Streamlit secrets first as a default
default_key = st.secrets.get("ODDS_API_KEY", "")

api_key = st.sidebar.text_input(
    "The Odds API Key",
    value=default_key,
    type="password",
    help="Get an API key at https://the-odds-api.com"
)

bankroll = st.sidebar.number_input("Bankroll ($)", value=1000.0, step=100.0)
kelly_fraction = st.sidebar.slider("Kelly Fraction (Risk)", 0.1, 1.0, 0.25, 0.05)
min_ev = st.sidebar.slider("Min +EV Threshold (%)", 0.0, 15.0, 1.5, 0.5)

selected_sports = st.sidebar.multiselect(
    "Select Sports",
    options=["baseball_mlb", "basketball_nba", "mma_mixed_martial_arts", "tennis_atp"],
    default=["baseball_mlb", "basketball_nba", "mma_mixed_martial_arts", "tennis_atp"],
    format_func=lambda x: {
        "baseball_mlb": "⚾ MLB",
        "basketball_nba": "🏀 NBA",
        "mma_mixed_martial_arts": "🥊 UFC / MMA",
        "tennis_atp": "🎾 Tennis (ATP)"
    }.get(x, x)
)

# ---------------------------------------------------------
# FETCH & PROCESS ODDS DATA
# ---------------------------------------------------------
ev_opportunities = []
total_games_scanned = 0
games_with_pinnacle = 0

if st.button("🚀 Scan Markets for +EV Bets", type="primary"):
    if not api_key:
        st.error("Please enter a valid API Key from The Odds API in the sidebar.")
    else:
        with st.spinner("Fetching market lines and stripping vig from sharp books..."):
            for sport in selected_sports:
                url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
                params = {
                    'apiKey': api_key,
                    'regions': 'us,eu',
                    'markets': 'h2h',
                    'oddsFormat': 'american'
                }
                
                try:
                    response = requests.get(url, params=params)
                    
                    # Track & display API quota usage in sidebar
                    requests_remaining = response.headers.get("x-requests-remaining")
                    requests_used = response.headers.get("x-requests-used")
                    if requests_remaining is not None:
                        st.sidebar.caption(f"📊 **Quota:** {requests_remaining} remaining ({requests_used} used)")

                    # Surface non-200 API errors directly to the UI
                    if response.status_code != 200:
                        err_msg = response.json().get('message', response.text)
                        st.error(f"⚠️ **API Error ({response.status_code})** for `{sport}`: {err_msg}")
                        continue

                    games = response.json()
                    total_games_scanned += len(games)

                except Exception as e:
                    st.error(f"Connection Error: {e}")
                    break

                for game in games:
                    home_team = game.get('home_team')
                    away_team = game.get('away_team')
                    
                    # Search for Pinnacle as the sharp benchmark
                    sharp_book = None
                    for book in game.get('bookmakers', []):
                        if book['key'] == 'pinnacle':
                            sharp_book = book
                            games_with_pinnacle += 1
                            break
                    
                    if not sharp_book:
                        continue
                    
                    # Extract sharp prices
                    sharp_outcomes = sharp_book['markets'][0]['outcomes']
                    if len(sharp_outcomes) != 2:
                        continue
                        
                    outcome_a, outcome_b = sharp_outcomes[0], sharp_outcomes[1]
                    
                    dec_a = american_to_decimal(outcome_a['price'])
                    dec_b = american_to_decimal(outcome_b['price'])
                    
                    imp_a = decimal_to_implied(dec_a)
                    imp_b = decimal_to_implied(dec_b)
                    
                    # Devig to get fair true probabilities
                    fair_prob_a, fair_prob_b = devig_multiplicative(imp_a, imp_b)
                    
                    fair_map = {
                        outcome_a['name']: fair_prob_a,
                        outcome_b['name']: fair_prob_b
                    }
                    
                    # Compare sharp fair prices against soft sportsbooks
                    for book in game.get('bookmakers', []):
                        if book['key'] == 'pinnacle':
                            continue
                        
                        book_name = book['title']
                        for outcome in book['markets'][0]['outcomes']:
                            team = outcome['name']
                            soft_american = outcome['price']
                            soft_decimal = american_to_decimal(soft_american)
                            
                            if team in fair_map:
                                true_prob = fair_map[team]
                                ev = calculate_ev(true_prob, soft_decimal)
                                ev_pct = ev * 100.0
                                
                                if ev_pct >= min_ev:
                                    kelly_pct = calculate_kelly(true_prob, soft_decimal, kelly_fraction)
                                    rec_stake = bankroll * kelly_pct
                                    
                                    ev_opportunities.append({
                                        "Sport": sport.upper().replace("_", " "),
                                        "Matchup": f"{away_team} @ {home_team}",
                                        "Selection": team,
                                        "Soft Sportsbook": book_name,
                                        "Soft Odds": f"{soft_american:+d}",
                                        "True Win Prob": f"{true_prob * 100:.2f}%",
                                        "+EV Edge": round(ev_pct, 2),
                                        "Rec Stake": f"${rec_stake:.2f} ({kelly_pct*100:.1f}%)"
                                    })

# ---------------------------------------------------------
# DISPLAY RESULTS
# ---------------------------------------------------------
if ev_opportunities:
    df = pd.DataFrame(ev_opportunities)
    df = df.sort_values(by="+EV Edge", ascending=False)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total +EV Plays Found", len(df))
    col2.metric("Highest Edge Found", f"{df['+EV Edge'].max()}%")
    col3.metric("Bankroll Size", f"${bankroll:,.2f}")
    
    st.subheader("🎯 Identified Positive Expected Value Plays")
    
    # Safe rendering in case matplotlib isn't installed
    try:
        st.dataframe(
            df.style.background_gradient(subset=["+EV Edge"], cmap="Greens"),
            use_container_width=True
        )
    except Exception:
        st.dataframe(df, use_container_width=True)

else:
    if total_games_scanned > 0:
        st.warning(f"Scanned **{total_games_scanned} games** across selected sports ({games_with_pinnacle} had Pinnacle odds posted), but no bets met your **+{min_ev}% EV** threshold.")
        st.info("💡 **Tip:** Try lowering your 'Min +EV Threshold (%)' slider to `0.0%` to view near-fair market lines.")
    else:
        st.info("Click 'Scan Markets for +EV Bets' to search for mispriced lines across selected sports.")
