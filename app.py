import streamlit as st
import pandas as pd
import numpy as np
import tweepy

st.set_page_config(page_title="OMEGA Sharp Terminal", layout="wide")

# ==========================================
# CORE MATH: DE-VIGGER & KELLY CALCULATORS
# ==========================================
def american_to_prob(odds):
    """Converts American odds to implied probability."""
    if odds < 0:
        return -odds / (-odds + 100)
    else:
        return 100 / (odds + 100)

def prob_to_american(prob):
    """Converts a true probability back to an American fair line."""
    if prob <= 0 or prob >= 1: return None
    if prob > 0.50:
        return int((prob / (1 - prob)) * -100)
    else:
        return int(((1 - prob) / prob) * 100)

def multiplicative_devig(odds1, odds2):
    """Strips the juice from sharp books to find the True Probability."""
    p1 = american_to_prob(odds1)
    p2 = american_to_prob(odds2)
    overround = p1 + p2
    true_p1 = p1 / overround
    true_p2 = p2 / overround
    return true_p1, true_p2

def calculate_ev(true_prob, retail_odds):
    """Calculates Expected Value (EV) against a retail book."""
    retail_p = american_to_prob(retail_odds)
    retail_decimal = 1 / retail_p
    ev = (true_prob * (retail_decimal - 1)) - (1 - true_prob)
    return ev * 100 # Return as percentage

def kelly_criterion(true_prob, retail_odds, bankroll, fraction=0.25):
    """Calculates the exact dollar amount to bet using Fractional Kelly."""
    retail_p = american_to_prob(retail_odds)
    b = (1 / retail_p) - 1
    q = 1 - true_prob
    kelly_pct = ((true_prob * b) - q) / b
    if kelly_pct <= 0:
        return 0.0
    return bankroll * (kelly_pct * fraction)


# ==========================================
# TWITTER / X API: BREAKING NEWS TRACKER
# ==========================================
def fetch_breaking_news(api_key, api_secret, access_token, access_secret, query):
    """
    Connects to X/Twitter API v2 to pull real-time injury/lineup news.
    Requires elevated X API developer credentials.
    """
    try:
        client = tweepy.Client(
            consumer_key=api_key, consumer_secret=api_secret,
            access_token=access_token, access_token_secret=access_secret
        )
        response = client.search_recent_tweets(query=query, max_results=10)
        if response.data:
            return [tweet.text for tweet in response.data]
        return ["No recent breaking news found for this query."]
    except Exception as e:
        return [f"API Authentication required or error occurred: {e}"]


# ==========================================
# UI FRONTEND & SPORT LOGIC
# ==========================================
st.title("⚡ OMEGA Syndicate: Market & EV Terminal")

# Sidebar Configuration
st.sidebar.header("Terminal Configuration")
bankroll = st.sidebar.number_input("Total Bankroll ($)", min_value=100.0, value=1500.0, step=100.0)
kelly_fraction = st.sidebar.selectbox("Kelly Multiplier", [0.10, 0.25, 0.50, 1.0], index=1)
sport_selection = st.sidebar.radio("Select Market:", ["Sharp De-Vigger (All Sports)", "MLB", "NBA", "UFC", "TENNIS"])

# --- TAB 1: THE SHARP DE-VIGGER ---
if sport_selection == "Sharp De-Vigger (All Sports)":
    st.header("The Institutional De-Vigger")
    st.markdown("Use this to strip the juice from **Pinnacle/Circa** and find mathematical edges at retail books.")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Sharp Book Inputs (Pinnacle/Circa)")
        sharp_fav = st.number_input("Sharp Favorite Odds", max_value=-101, value=-150, step=1)
        sharp_dog = st.number_input("Sharp Underdog Odds", min_value=100, value=135, step=1)
    with col2:
        st.subheader("Retail Book Inputs (DK/FD)")
        retail_odds = st.number_input("Available Retail Odds on your pick", value=-130, step=1)
        pick_side = st.radio("Which side are you betting?", ["Favorite", "Underdog"])

    if st.button("Audit Market Value"):
        true_fav, true_dog = multiplicative_devig(sharp_fav, sharp_dog)
        target_prob = true_fav if pick_side == "Favorite" else true_dog
        
        ev_pct = calculate_ev(target_prob, retail_odds)
        rec_bet = kelly_criterion(target_prob, retail_odds, bankroll, kelly_fraction)
        
        st.divider()
        # Chart / Table Output over raw text for cleaner UI
        results_df = pd.DataFrame({
            "Metric": ["True Probability", "Fair American Line", "Expected Value (EV)", "Recommended Stake"],
            "Value": [
                f"{target_prob*100:.2f}%", 
                f"{prob_to_american(target_prob)}", 
                f"{ev_pct:.2f}%", 
                f"${rec_bet:.2f}"
            ]
        })
        st.table(results_df)
        
        if ev_pct > 0:
            st.success("🔥 MATHEMATICAL EDGE IDENTIFIED. GREEN LIGHT TO EXECUTE.")
        else:
            st.error("⚠️ NEGATIVE EV. PASS ON THIS BET.")

# --- TAB 2: MLB ---
elif sport_selection == "MLB":
    st.header("MLB: First 5 (F5) Isolation Engine")
    st.markdown("> **SHARP RULE:** Never bet full game moneylines without modeling the bullpen. Isolate starting pitchers using F5 lines, SIERA, and recent 14-day wRC+ splits.")
    
    col1, col2 = st.columns(2)
    with col1:
        away_siera = st.number_input("Away Pitcher SIERA", value=3.50, step=0.10)
        away_wrc = st.number_input("Away Lineup 14-Day wRC+", value=105, step=1)
    with col2:
        home_siera = st.number_input("Home Pitcher SIERA", value=4.10, step=0.10)
        home_wrc = st.number_input("Home Lineup 14-Day wRC+", value=95, step=1)
        
    st.info("Note: This UI is designed to collect data for your regression models. Track these specific metrics daily to find deviations from the market.")

# --- TAB 3: NBA ---
elif sport_selection == "NBA":
    st.header("NBA: Pace & Rest Adjusted Terminal")
    st.markdown("> **SHARP RULE:** The NBA market is beaten by tracking injuries and rest advantages (B2B penalties). Raw points per game is garbage; track Pace-Adjusted Net Rating.")
    
    st.subheader("Live Breaking News Feed (X API)")
    x_query = st.text_input("Search Twitter for injury news (e.g., 'Embiid out', 'Shams charania')", value="NBA injury OR out")
    if st.button("Fetch X Feed"):
        # You will need to add your actual API keys here to go live.
        st.write("Connecting to X API...")
        news = fetch_breaking_news("API_KEY", "API_SECRET", "TOKEN", "TOKEN_SECRET", x_query)
        for update in news:
            st.write(f"- {update}")

# --- TAB 4: UFC ---
elif sport_selection == "UFC":
    st.header("UFC: Combat Analytics")
    st.markdown("> **SHARP RULE:** Value in MMA is found in duration props (Over/Under rounds) and fading older fighters. The golden rule: Fade fighters coming off a 365+ day layoff or aged 35+ in lighter weight classes.")
    
    st.write("Input Fighter Strike Differentials (SLpM - SApM) and Takedown Averages to model pace and output projected finish probabilities.")
    # Placeholders for combat inputs
    f1_strike_diff = st.number_input("Fighter A Strike Differential", value=1.5, step=0.1)
    f2_strike_diff = st.number_input("Fighter B Strike Differential", value=-0.5, step=0.1)

# --- TAB 5: TENNIS ---
elif sport_selection == "TENNIS":
    st.header("TENNIS: Surface & Hold % Engine")
    st.markdown("> **SHARP RULE:** Never use generic global rankings. Tennis models must separate Hard Court, Clay, and Grass Elo ratings. Track Dominance Ratio (Return points won / Serve points lost).")
    
    t_surface = st.selectbox("Court Surface", ["Hard", "Clay", "Grass"])
    st.write(f"Ensure you are pulling {t_surface}-specific Hold/Break percentages for accurate calculations.")
