import streamlit as st
import pandas as pd
import numpy as np
import requests

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
    if prob <= 0 or prob >= 1: 
        return "N/A"
    prob = np.clip(prob, 0.01, 0.99)
    if prob >= 0.50:
        return int(round((prob / (1 - prob)) * -100))
    else:
        return int(round(((1 - prob) / prob) * 100))

def multiplicative_devig(odds1, odds2):
    """Strips the juice from sharp books using multiplicative method."""
    p1 = american_to_prob(odds1)
    p2 = american_to_prob(odds2)
    overround = p1 + p2
    if overround == 0:
        return 0.5, 0.5
    return p1 / overround, p2 / overround

def calculate_ev(true_prob, retail_odds):
    """Calculates Expected Value (EV) against a retail book."""
    retail_p = american_to_prob(retail_odds)
    if retail_p == 0:
        return 0.0
    retail_decimal = 1 / retail_p
    ev = (true_prob * (retail_decimal - 1)) - (1 - true_prob)
    return ev * 100

def kelly_criterion(true_prob, retail_odds, bankroll, fraction=0.25):
    """Calculates exact dollar stake using Fractional Kelly."""
    retail_p = american_to_prob(retail_odds)
    if retail_p == 0:
        return 0.0
    b = (1 / retail_p) - 1
    q = 1 - true_prob
    if b <= 0:
        return 0.0
    kelly_pct = ((true_prob * b) - q) / b
    if kelly_pct <= 0:
        return 0.0
    return bankroll * (kelly_pct * fraction)


# ==========================================
# UI FRONTEND & SPORT LOGIC
# ==========================================
st.title("⚡ OMEGA Syndicate: Market & EV Terminal")

# Sidebar Configuration
st.sidebar.header("Terminal Configuration")
bankroll = st.sidebar.number_input("Total Bankroll ($)", min_value=100.0, value=1000.0, step=100.0)
kelly_fraction = st.sidebar.selectbox("Kelly Multiplier", [0.10, 0.25, 0.50, 1.0], index=1)
sport_selection = st.sidebar.radio("Select Market:", [
    "Sharp De-Vigger (All Sports)", 
    "MLB (First 5 Isolation)", 
    "NBA (Rest & Pace)", 
    "UFC (Combat Analytics)", 
    "TENNIS (Surface Elo)"
])

# --- TAB 1: THE SHARP DE-VIGGER ---
if sport_selection == "Sharp De-Vigger (All Sports)":
    st.header("The Institutional De-Vigger")
    st.markdown("Strip juice from sharp books (Pinnacle/Circa) to find true market probabilities and hunt retail misprices.")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Sharp Market Line (Pinnacle/Circa)")
        sharp_fav = st.number_input("Sharp Favorite Odds", max_value=-101, value=-150, step=1)
        sharp_dog = st.number_input("Sharp Underdog Odds", min_value=100, value=130, step=1)
    with col2:
        st.subheader("Retail Line Available to Bet")
        retail_odds = st.number_input("Your Retail Book Odds (DK/FD/Caesars)", value=-125, step=1)
        pick_side = st.radio("Which side are you betting?", ["Favorite", "Underdog"])

    if st.button("Audit Market Value"):
        true_fav, true_dog = multiplicative_devig(sharp_fav, sharp_dog)
        target_prob = true_fav if pick_side == "Favorite" else true_dog
        
        ev_pct = calculate_ev(target_prob, retail_odds)
        rec_bet = kelly_criterion(target_prob, retail_odds, bankroll, kelly_fraction)
        
        st.divider()
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("True Probability", f"{target_prob*100:.2f}%")
        c2.metric("True Fair Line", f"{prob_to_american(target_prob):+d}" if isinstance(prob_to_american(target_prob), int) else "N/A")
        c3.metric("Expected Value (EV)", f"{ev_pct:+.2f}%")
        c4.metric("Recommended Stake", f"${rec_bet:.2f}")

        if ev_pct >= 3.0:
            st.success(f"🔥 HIGH VALUE EDGE: +{ev_pct:.2f}% EV. Recommended bet size: **${rec_bet:.2f}**.")
        elif ev_pct > 0:
            st.info(f"✅ MARGINAL EDGE: +{ev_pct:.2f}% EV. Recommended bet size: **${rec_bet:.2f}**.")
        else:
            st.error(f"🛑 NEGATIVE EV ({ev_pct:.2f}%): Do not place this bet.")

# --- TAB 2: MLB ---
elif sport_selection == "MLB (First 5 Isolation)":
    st.header("⚾ MLB: First 5 (F5) Isolation Engine")
    st.caption("SHARP RULE: Isolate starting pitchers using F5 lines, SIERA, and 14-day wRC+ to eliminate bullpen volatility.")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Away Team")
        away_name = st.text_input("Away Team", "Away")
        away_siera = st.number_input("Away Pitcher SIERA", value=3.50, step=0.05)
        away_wrc = st.number_input("Away Lineup 14-Day wRC+", value=105.0, step=1.0)
    with col2:
        st.subheader("Home Team")
        home_name = st.text_input("Home Team", "Home")
        home_siera = st.number_input("Home Pitcher SIERA", value=4.10, step=0.05)
        home_wrc = st.number_input("Home Lineup 14-Day wRC+", value=95.0, step=1.0)

    if st.button("Calculate MLB F5 Fair Line"):
        pitching_diff = home_siera - away_siera
        offense_diff = (away_wrc - home_wrc) / 100.0
        logit_score = 0.12 + (pitching_diff * 0.35) + (offense_diff * 0.25)
        
        away_prob = 1 / (1 + np.exp(logit_score))
        home_prob = 1 - away_prob

        st.divider()
        m1, m2 = st.columns(2)
        m1.metric(f"{away_name} F5 Win Prob", f"{away_prob*100:.1f}%", f"{prob_to_american(away_prob):+d}")
        m2.metric(f"{home_name} F5 Win Prob", f"{home_prob*100:.1f}%", f"{prob_to_american(home_prob):+d}")

# --- TAB 3: NBA ---
elif sport_selection == "NBA (Rest & Pace)":
    st.header("🏀 NBA: Rest & Net Rating Model")
    st.caption("SHARP RULE: Track Back-to-Back (B2B) rest penalties and Net Ratings rather than raw points.")
    
    col1, col2 = st.columns(2)
    with col1:
        away_net = st.number_input("Away Net Rating", value=3.2, step=0.1)
        away_rest = st.number_input("Away Rest Days (0 = B2B)", value=1, step=1)
    with col2:
        home_net = st.number_input("Home Net Rating", value=-1.0, step=0.1)
        home_rest = st.number_input("Home Rest Days (0 = B2B)", value=2, step=1)
        
    hca = st.slider("Home Court Advantage (Points)", 1.0, 4.0, 2.5, step=0.1)

    if st.button("Calculate NBA Fair Line"):
        rest_diff = home_rest - away_rest
        adj_diff = (home_net - away_net) + hca + (rest_diff * 0.75)
        home_prob = 1 / (1 + np.exp(-adj_diff * 0.15))
        away_prob = 1 - home_prob

        st.divider()
        n1, n2 = st.columns(2)
        n1.metric("Away Fair Win Prob", f"{away_prob*100:.1f}%", f"{prob_to_american(away_prob):+d}")
        n2.metric("Home Fair Win Prob", f"{home_prob*100:.1f}%", f"{prob_to_american(home_prob):+d}")

# --- TAB 4: UFC ---
elif sport_selection == "UFC (Combat Analytics)":
    st.header("🥊 UFC: Strike Differential Model")
    st.caption("SHARP RULE: Model strike output differential (SLpM - SApM) and penalize fighters aged 35+ in lighter divisions.")
    
    col1, col2 = st.columns(2)
    with col1:
        f1_slpm = st.number_input("Fighter A SLpM", value=4.10)
        f1_sapm = st.number_input("Fighter A SApM", value=2.50)
    with col2:
        f2_slpm = st.number_input("Fighter B SLpM", value=3.20)
        f2_sapm = st.number_input("Fighter B SApM", value=3.80)

    if st.button("Calculate UFC Matchup"):
        f1_diff = f1_slpm - f1_sapm
        f2_diff = f2_slpm - f2_sapm
        prob_f1 = 1 / (1 + np.exp(-(f1_diff - f2_diff)))
        prob_f2 = 1 - prob_f1

        st.divider()
        u1, u2 = st.columns(2)
        u1.metric("Fighter A Win Prob", f"{prob_f1*100:.1f}%", f"{prob_to_american(prob_f1):+d}")
        u2.metric("Fighter B Win Prob", f"{prob_f2*100:.1f}%", f"{prob_to_american(prob_f2):+d}")

# --- TAB 5: TENNIS ---
elif sport_selection == "TENNIS (Surface Elo)":
    st.header("🎾 Tennis: Surface Elo Engine")
    st.caption("SHARP RULE: Never use generic ATP rankings. Evaluate surface-specific Elo and Hold/Break percentages.")
    
    surface = st.selectbox("Court Surface", ["Hard", "Clay", "Grass"])
    col1, col2 = st.columns(2)
    with col1:
        p1_elo = st.number_input("Player 1 Surface Elo", value=1850)
        p1_hb = st.number_input("P1 (Hold % + Break %)", value=105.0)
    with col2:
        p2_elo = st.number_input("Player 2 Surface Elo", value=1720)
        p2_hb = st.number_input("P2 (Hold % + Break %)", value=98.0)

    if st.button("Calculate Tennis Fair Line"):
        elo_diff = p1_elo - p2_elo
        p1_base = 1 / (1 + 10 ** (-elo_diff / 400.0))
        skill_adj = (p1_hb - p2_hb) / 200.0
        p1_prob = np.clip(p1_base + skill_adj, 0.05, 0.95)
        p2_prob = 1.0 - p1_prob

        st.divider()
        t1, t2 = st.columns(2)
        t1.metric("Player 1 Fair Line", f"{p1_prob*100:.1f}%", f"{prob_to_american(p1_prob):+d}")
        t2.metric("Player 2 Fair Line", f"{p2_prob*100:.1f}%", f"{prob_to_american(p2_prob):+d}")
