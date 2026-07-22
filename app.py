import streamlit as st
import numpy as np
import requests

st.set_page_config(page_title="OMEGA Sharp Analytics Engine", layout="wide")

# Pre-loaded default Odds API Key
DEFAULT_API_KEY = "c17801d71f4342ca1dd66536e9b62634"

st.title("⚡ OMEGA Multi-Sport EV, Devig & Staking Engine")
st.markdown("---")

# ---------------------------------------------------------
# CORE MATH, DEVIGGING & STAKING FUNCTIONS
# ---------------------------------------------------------
def prob_to_american(p):
    # Dynamic clamping completely prevents unadjusted static values (e.g., -365 bugs)
    p = np.clip(p, 0.01, 0.99)
    if p >= 0.5:
        return int(round(-100 * (p / (1 - p))))
    else:
        return int(round(100 * ((1 - p) / p)))

def american_to_decimal(odds):
    if odds > 0:
        return (odds / 100.0) + 1.0
    elif odds < 0:
        return (100.0 / abs(odds)) + 1.0
    return 1.0

def power_devig(odds1_amer, odds2_amer):
    """
    Strips bookmaker vig using the Power Method.
    Accounts for favorite-longshot bias and keeps probabilities within 0-1.
    """
    p1 = 1.0 / american_to_decimal(odds1_amer)
    p2 = 1.0 / american_to_decimal(odds2_amer)
    
    # Bisection search to find exponent k where p1^k + p2^k = 1
    low, high = 0.001, 10.0
    for _ in range(50):
        mid = (low + high) / 2.0
        if (p1**mid + p2**mid) > 1.0:
            low = mid
        else:
            high = mid
    k = (low + high) / 2.0
    return p1**k, p2**k

def calculate_ev(win_prob, decimal_odds):
    return (win_prob * (decimal_odds - 1)) - (1 - win_prob)

def kelly_criterion(win_prob, decimal_odds, fraction, bankroll):
    b = decimal_odds - 1.0
    q = 1.0 - win_prob
    if b <= 0:
        return 0.0
    k_star = (b * win_prob - q) / b
    return max(0.0, k_star * fraction * bankroll)

@st.cache_data(ttl=120)
def fetch_live_odds(api_key, sport_key):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {
        "apiKey": api_key,
        "regions": "us",
        "markets": "h2h", 
        "oddsFormat": "american"
    }
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None

def find_best_odds(game_data):
    best_home = -10000
    best_away = -10000
    home_book = "N/A"
    away_book = "N/A"
    
    for book in game_data.get("bookmakers", []):
        for market in book.get("markets", []):
            if market["key"] == "h2h":
                for outcome in market["outcomes"]:
                    price = outcome["price"]
                    if outcome["name"] == game_data["home_team"]:
                        if price > best_home:
                            best_home = price
                            home_book = book["title"]
                    else:
                        if price > best_away:
                            best_away = price
                            away_book = book["title"]
                            
    return {"home_odds": best_home, "home_book": home_book, 
            "away_odds": best_away, "away_book": away_book}

# ---------------------------------------------------------
# SIDEBAR CONFIGURATION
# ---------------------------------------------------------
st.sidebar.header("⚙️ System Configuration")
api_key = st.sidebar.text_input("Odds API Key", value=DEFAULT_API_KEY, type="password")

st.sidebar.markdown("---")
st.sidebar.header("💰 Bankroll Management")
total_bankroll = st.sidebar.number_input("Total Bankroll ($)", value=1000.0, step=100.0)
kelly_fraction = st.sidebar.selectbox("Kelly Multiplier", [0.10, 0.25, 0.50, 1.0], index=1)

sport = st.sidebar.selectbox("Select Analytics Model", [
    "MLB (Quantitative Edge)", 
    "NBA (Pace & Net Rating)", 
    "UFC (Algorithmic Fight)", 
    "Tennis (Surface Elo)"
])

# ---------------------------------------------------------
# 1. MLB SHARP MODEL
# ---------------------------------------------------------
if sport == "MLB (Quantitative Edge)":
    st.header("⚾ MLB OMEGA Model")
    
    if api_key:
        with st.expander("📡 Live MLB Outlier Scanner", expanded=True):
            odds_data = fetch_live_odds(api_key, "baseball_mlb")
            if odds_data:
                for game in odds_data:
                    best_lines = find_best_odds(game)
                    if best_lines["home_odds"] != -10000:
                        st.markdown(f"**{game['away_team']} @ {game['home_team']}**")
                        st.write(f"- 📈 Best Away: **{best_lines['away_odds']:+d}** ({best_lines['away_book']}) | Best Home: **{best_lines['home_odds']:+d}** ({best_lines['home_book']})")
                st.divider()
            else:
                st.error("Failed to fetch odds. Verify your API Key or endpoint limits.")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Away Team Inputs")
        away_team = st.text_input("Away Team Name", "Away")
        away_pitcher_siera = st.number_input("Away Pitcher SIERA / xFIP", value=3.80, step=0.05)
        away_wrc = st.number_input("Away 14-Day wRC+", value=102.0, step=1.0)
        
    with col2:
        st.subheader("Home Team Inputs")
        home_team = st.text_input("Home Team Name", "Home")
        home_pitcher_siera = st.number_input("Home Pitcher SIERA / xFIP", value=4.50, step=0.05)
        home_wrc = st.number_input("Home 14-Day wRC+", value=98.0, step=1.0)

    if st.button("Calculate MLB Fair Edge"):
        pitching_diff = home_pitcher_siera - away_pitcher_siera
        offense_diff = (away_wrc - home_wrc) / 100.0
        logit_score = 0.12 + (pitching_diff * 0.35) + (offense_diff * 0.25)
        
        away_win_prob = 1 / (1 + np.exp(logit_score))
        home_win_prob = 1 - away_win_prob

        st.markdown("---")
        res1, res2 = st.columns(2)
        res1.metric(f"{away_team} Win Prob / Fair Line", f"{away_win_prob*100:.1f}%", f"{prob_to_american(away_win_prob):+d}")
        res2.metric(f"{home_team} Win Prob / Fair Line", f"{home_win_prob*100:.1f}%", f"{prob_to_american(home_win_prob):+d}")

# ---------------------------------------------------------
# 2. NBA SHARP MODEL
# ---------------------------------------------------------
elif sport == "NBA (Pace & Net Rating)":
    st.header("🏀 NBA OMEGA Model")
    
    if api_key:
        with st.expander("📡 Live NBA Outlier Scanner", expanded=True):
            odds_data = fetch_live_odds(api_key, "basketball_nba")
            if odds_data:
                for game in odds_data:
                    best_lines = find_best_odds(game)
                    if best_lines["home_odds"] != -10000:
                        st.markdown(f"**{game['away_team']} @ {game['home_team']}**")
                        st.write(f"- 📈 Best Away: **{best_lines['away_odds']:+d}** ({best_lines['away_book']}) | Best Home: **{best_lines['home_odds']:+d}** ({best_lines['home_book']})")
                st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Away Team Inputs")
        away_team = st.text_input("Away Team Name", "Away")
        away_net_rating = st.number_input("Away Net Rating", value=2.5, step=0.1)
        away_rest_days = st.number_input("Away Rest Days (0 = B2B)", value=1, step=1)
        
    with col2:
        st.subheader("Home Team Inputs")
        home_team = st.text_input("Home Team Name", "Home")
        home_net_rating = st.number_input("Home Net Rating", value=-1.2, step=0.1)
        home_rest_days = st.number_input("Home Rest Days (0 = B2B)", value=2, step=1)
        
    hca_points = st.slider("Home Court Advantage (Points)", 1.0, 4.0, 2.5, step=0.1)

    if st.button("Calculate NBA Fair Edge"):
        # Calculate rest advantage (positive means home has rest advantage)
        rest_diff = home_rest_days - away_rest_days
        rest_penalty = rest_diff * 0.75 # 0.75 points per day of rest advantage
        
        # Calculate adjusted Net Rating difference factoring in HCA and Rest
        adjusted_diff = (home_net_rating - away_net_rating) + hca_points + rest_penalty
        
        # Logistic curve conversion for basketball scores (0.15 scalar for NBA variance)
        home_win_prob = 1 / (1 + np.exp(-adjusted_diff * 0.15))
        away_win_prob = 1 - home_win_prob

        st.markdown("---")
        res1, res2 = st.columns(2)
        res1.metric(f"{away_team} Win Prob / Fair Line", f"{away_win_prob*100:.1f}%", f"{prob_to_american(away_win_prob):+d}")
        res2.metric(f"{home_team} Win Prob / Fair Line", f"{home_win_prob*100:.1f}%", f"{prob_to_american(home_win_prob):+d}")

# ---------------------------------------------------------
# 3. UFC SHARP MODEL
# ---------------------------------------------------------
elif sport == "UFC (Algorithmic Fight)":
    st.header("🥊 UFC OMEGA Model")
    
    if api_key:
        with st.expander("📡 Live UFC Outlier Scanner", expanded=True):
            odds_data = fetch_live_odds(api_key, "mma_mixed_martial_arts")
            if odds_data:
                for fight in odds_data:
                    best_lines = find_best_odds(fight)
                    if best_lines["home_odds"] != -10000:
                        st.markdown(f"**{fight['away_team']} vs {fight['home_team']}**")
                        st.write(f"- 📈 Best {fight['away_team']}: **{best_lines['away_odds']:+d}** ({best_lines['away_book']}) | Best {fight['home_team']}: **{best_lines['home_odds']:+d}** ({best_lines['home_book']})")
                st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Fighter A")
        f1_name = st.text_input("Name", "Fighter A")
        f1_slpm = st.number_input("Fighter A SLpM", value=3.64)
        f1_sapm = st.number_input("Fighter A SApM", value=2.25)

    with col2:
        st.subheader("Fighter B")
        f2_name = st.text_input("Name", "Fighter B")
        f2_slpm = st.number_input("Fighter B SLpM", value=4.10)
        f2_sapm = st.number_input("Fighter B SApM", value=3.80)

    if st.button("Evaluate UFC Matchup"):
        f1_diff = f1_slpm - f1_sapm
        f2_diff = f2_slpm - f2_sapm
        prob_f1 = 1 / (1 + np.exp(-(f1_diff - f2_diff)))
        prob_f2 = 1 - prob_f1
        
        st.markdown("---")
        u_col1, u_col2 = st.columns(2)
        u_col1.metric(f"{f1_name} Fair Odds", f"{prob_f1*100:.1f}%", f"{prob_to_american(prob_f1):+d}")
        u_col2.metric(f"{f2_name} Fair Odds", f"{prob_f2*100:.1f}%", f"{prob_to_american(prob_f2):+d}")

# ---------------------------------------------------------
# 4. TENNIS SHARP MODEL
# ---------------------------------------------------------
elif sport == "Tennis (Surface Elo)":
    st.header("🎾 Tennis OMEGA Model")
    
    if api_key:
        with st.expander("📡 Live Tennis Outlier Scanner", expanded=True):
            odds_data = fetch_live_odds(api_key, "tennis_atp")
            if odds_data:
                for match in odds_data:
                    best_lines = find_best_odds(match)
                    if best_lines["home_odds"] != -10000:
                        st.markdown(f"**{match['away_team']} vs {match['home_team']}**")
                        st.write(f"- 📈 Best {match['away_team']}: **{best_lines['away_odds']:+d}** ({best_lines['away_book']}) | Best {match['home_team']}: **{best_lines['home_odds']:+d}** ({best_lines['home_book']})")
                st.divider()

    surface = st.selectbox("Court Surface", ["Hard", "Clay", "Grass"])
    
    col1, col2 = st.columns(2)
    with col1:
        p1_name = st.text_input("Player 1", "Player A")
        p1_elo = st.number_input("Player 1 Surface Elo", value=1850)
        p1_hold_break = st.number_input("P1 (Hold % + Break %)", value=105.0) 
    with col2:
        p2_name = st.text_input("Player 2", "Player B")
        p2_elo = st.number_input("Player 2 Surface Elo", value=1720)
        p2_hold_break = st.number_input("P2 (Hold % + Break %)", value=98.0)

    if st.button("Calculate Tennis Odds"):
        # Standard Elo base calculation
        elo_diff = p1_elo - p2_elo
        p1_elo_prob = 1 / (1 + 10 ** (-elo_diff / 400.0))
        
        # Micro-adjustment based on surface-specific Hold/Break proficiency
        skill_adj = (p1_hold_break - p2_hold_break) / 200.0
        
        # Combine and clamp logic completely removes static value errors
        final_p1_prob = np.clip(p1_elo_prob + skill_adj, 0.05, 0.95)
        final_p2_prob = 1.0 - final_p1_prob
        
        st.markdown("---")
        t_col1, t_col2 = st.columns(2)
        t_col1.metric(f"{p1_name} Fair Odds", f"{final_p1_prob*100:.1f}%", f"{prob_to_american(final_p1_prob):+d}")
        t_col2.metric(f"{p2_name} Fair Odds", f"{final_p2_prob*100:.1f}%", f"{prob_to_american(final_p2_prob):+d}")

# ---------------------------------------------------------
# GLOBAL EV & KELLY STAKING CALCULATOR
# ---------------------------------------------------------
st.markdown("---")
st.header("📈 Institutional Value & Staking Audit")
st.markdown("Run your Sharp Market De-Vig or calculate edge against retail books.")

tab1, tab2 = st.tabs(["EV & Staking (Bet Sizing)", "Power Method De-Vigger (Find True Probability)"])

with tab1:
    ev_col1, ev_col2, ev_col3, ev_col4 = st.columns(4)
    with ev_col1:
        model_prob = st.number_input("Your Model Win Prob (%)", value=62.5, min_value=1.0, max_value=99.0) / 100.0
    with ev_col2:
        book_odds = st.number_input("Best Book Odds (American)", value=-115)
    with ev_col3:
        dec_odds = american_to_decimal(book_odds)
        ev_val = calculate_ev(model_prob, dec_odds) * 100
        st.metric("Expected Value (EV %)", f"{ev_val:+.2f}%")
    with ev_col4:
        suggested_stake = kelly_criterion(model_prob, dec_odds, kelly_fraction, total_bankroll)
        st.metric("Recommended Stake", f"${suggested_stake:.2f}")

    if ev_val > 3.0:
        st.success(f"🔥 MASSIVE EDGE: +{ev_val:.2f}% EV detected. Recommended bet size: **${suggested_stake:.2f}**.")
    elif ev_val > 0.0:
        st.info(f"✅ MARGINAL EDGE: +{ev_val:.2f}% EV detected. Recommended bet size: **${suggested_stake:.2f}**.")
    else:
        st.error(f"🛑 NEGATIVE VALUE: Do not place this bet. EV is {ev_val:.2f}%.")

with tab2:
    st.markdown("Enter sharp sportsbook odds (e.g. Circa or Pinnacle) to strip the vig and find the true market probability.")
    dv_col1, dv_col2, dv_col3 = st.columns(3)
    with dv_col1:
        sharp_fav = st.number_input("Sharp Favorite Odds", value=-150)
    with dv_col2:
        sharp_dog = st.number_input("Sharp Underdog Odds", value=130)
    with dv_col3:
        if st.button("Run Power De-Vig"):
            true_fav, true_dog = power_devig(sharp_fav, sharp_dog)
            st.success(f"**True Fav Prob:** {true_fav*100:.2f}% (Fair Line: {prob_to_american(true_fav)})\n\n**True Dog Prob:** {true_dog*100:.2f}% (Fair Line: {prob_to_american(true_dog)})")
