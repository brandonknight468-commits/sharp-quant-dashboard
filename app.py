import streamlit as st

def prob_to_american(prob):
    """Converts win probability (0 to 1) into standard American odds."""
    if prob >= 0.5:
        return int(-100 * (prob / (1 - prob)))
    else:
        return int(100 * ((1 - prob) / prob))

# Dashboard Config
st.set_page_config(page_title="Sharp Quant Dashboard", layout="wide")
st.title("⚡ Sharp Multi-Sport Predictive Dashboard")

tab1, tab2, tab3, tab4 = st.tabs([
    "⚾ MLB (F5 Model)", 
    "🥊 UFC (Style Analyzer)", 
    "🏀 NBA (Injury Adjuster)", 
    "🎾 Tennis (Live Validator)"
])

# =========================================================
# TAB 1: MLB FIRST 5 INNINGS (F5) MODEL (FULLY CORRECTED)
# =========================================================
with tab1:
    st.header("⚾ MLB First 5 Innings (F5) Model")
    st.caption("Calibrated for 5-inning variance using Pythagenpat exponent scaling (γ = 1.20) and weighted wRC+ regression.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Team A (Away)")
        team_a_name = st.text_input("Team A Name", value="Dodgers")
        a_wrc_season = st.number_input("Team A Season wRC+", value=115.0, step=1.0)
        a_wrc_14d = st.number_input("Team A 14-Day wRC+", value=100.0, step=1.0)
        a_sp_xfip = st.number_input("Team A Pitcher xFIP", value=3.31, step=0.01)
        
    with col2:
        st.subheader("Team B (Home)")
        team_b_name = st.text_input("Team B Name", value="Yankees")
        b_wrc_season = st.number_input("Team B Season wRC+", value=110.0, step=1.0)
        b_wrc_14d = st.number_input("Team B 14-Day wRC+", value=101.0, step=1.0)
        b_sp_xfip = st.number_input("Team B Pitcher xFIP", value=5.26, step=0.01)

    if st.button("Calculate MLB F5 True Odds"):
        # 1. Regress wRC+ (65% Season / 35% 14-Day)
        a_wrc_eff = (0.65 * a_wrc_season) + (0.35 * a_wrc_14d)
        b_wrc_eff = (0.65 * b_wrc_season) + (0.35 * b_wrc_14d)
        
        # 2. MATCHUP CROSS-OVER:
        # Team A hits against Team B's Pitcher (b_sp_xfip)
        a_exp_runs = 2.4 * (a_wrc_eff / 100.0) * (b_sp_xfip / 4.00)
        
        # Team B hits against Team A's Pitcher (a_sp_xfip)
        b_exp_runs = 2.4 * (b_wrc_eff / 100.0) * (a_sp_xfip / 4.00)
        
        # 3. Scaled Pythagorean Win Expectancy (gamma = 1.20)
        gamma = 1.20
        a_win_prob = (a_exp_runs ** gamma) / ((a_exp_runs ** gamma) + (b_exp_runs ** gamma))
        
        a_american = prob_to_american(a_win_prob)
        b_american = prob_to_american(1 - a_win_prob)
        
        st.markdown("---")
        # Direct string formatting for standard American odds (+ or - based on the returned int)
        st.metric(f"{team_a_name} True Moneyline", f"{a_american:+d}", f"{a_win_prob*100:.1f}% Win Prob")
        st.metric(f"{team_b_name} True Moneyline", f"{b_american:+d}", f"{(1-a_win_prob)*100:.1f}% Win Prob")
        st.info(f"Projected F5 Runs: {team_a_name} {a_exp_runs:.2f} - {b_exp_runs:.2f} {team_b_name}")

# =========================================================
# TAB 2: UFC STYLISTIC ANALYZER
# =========================================================
with tab2:
    st.header("🥊 UFC Stylistic Matchup Analyzer")
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Fighter A (Favorite / Striker)")
        f_a_slpm = st.number_input("SLpM (Strikes Landed/min)", value=4.50, key="a_slpm")
        f_a_sapm = st.number_input("SApM (Strikes Absorbed/min)", value=3.80, key="a_sapm")
        f_a_td_avg = st.number_input("TD Avg (Takedowns/15m)", value=0.50, key="a_td")
        f_a_td_def = st.number_input("TD Def %", value=60.0, key="a_tdd")
        
    with c2:
        st.subheader("Fighter B (Underdog / Grappler)")
        f_b_slpm = st.number_input("SLpM (Strikes Landed/min)", value=2.80, key="b_slpm")
        f_b_sapm = st.number_input("SApM (Strikes Absorbed/min)", value=2.10, key="b_sapm")
        f_b_td_avg = st.number_input("TD Avg (Takedowns/15m)", value=3.20, key="b_td")
        f_b_td_def = st.number_input("TD Def %", value=75.0, key="b_tdd")

    if st.button("Run UFC Stylistic Check"):
        st.markdown("---")
        diff_a = f_a_slpm - f_a_sapm
        diff_b = f_b_slpm - f_b_sapm
        
        st.write(f"**Fighter A Striking Differential:** {diff_a:+.2f}")
        st.write(f"**Fighter B Striking Differential:** {diff_b:+.2f}")
        
        if f_b_td_avg >= 2.50 and f_a_td_def < 65.0:
            st.error("🔥 STRUCTURAL EDGE FOUND: Fighter B (Grappler) has a massive stylistic advantage over Fighter A's weak Takedown Defense (<65%). High +EV potential on Fighter B.")
        elif f_a_td_avg >= 2.50 and f_b_td_def < 65.0:
            st.error("🔥 STRUCTURAL EDGE FOUND: Fighter A (Grappler) has a dominant matchup over Fighter B's TDD.")
        else:
            st.success("✅ Market Balanced: No severe stylistic mismatch detected. Line is likely efficient.")

# =========================================================
# TAB 3: NBA INJURY ADJUSTER
# =========================================================
with tab3:
    st.header("🏀 NBA Live/Pre-Game Injury Line Adjuster")
    
    col_n1, col_n2 = st.columns(2)
    with col_n1:
        base_spread = st.number_input("Baseline Pinnacle Spread (e.g. -5.5 for Favorite)", value=-5.5)
        player_tier = st.selectbox("Injured Player Tier", [
            "Tier 1: MVP / Top 5 Player (~4.5 pts)",
            "Tier 2: All-Star (~2.5 pts)",
            "Tier 3: Key Starter (~1.25 pts)"
        ])
        team_affected = st.radio("Team Affected", ["Favorite Injured", "Underdog Injured"])
    
    with col_n2:
        minutes_left = st.slider("Minutes Remaining in Game", min_value=0, max_value=48, value=48)
    
    if st.button("Calculate Adjusted Spread"):
        tier_val = 4.5 if "Tier 1" in player_tier else (2.5 if "Tier 2" in player_tier else 1.25)
        
        time_fraction = minutes_left / 48.0
        effective_points = tier_val * time_fraction
        
        if team_affected == "Favorite Injured":
            adjusted_spread = base_spread + effective_points
        else:
            adjusted_spread = base_spread - effective_points
            
        st.markdown("---")
        st.subheader(f"True Adjusted Spread: **{adjusted_spread:+.1f}**")
        st.caption(f"Impact: {effective_points:.2f} points adjusted for {minutes_left} minutes remaining.")

# =========================================================
# TAB 4: TENNIS LIVE SWING VALIDATOR
# =========================================================
with tab4:
    st.header("🎾 Tennis Live Psychological Swing Validator")
    st.caption("Valid for ATP/WTA 500, 1000, and Grand Slams ONLY (Requires verified UE/Winner stats).")
    
    pre_odds = st.number_input("Pre-Match Odds of Favorite (e.g. -250)", value=-250)
    surface_win_pct = st.number_input("Favorite Career Win % on Surface", value=70.0)
    
    c_t1, c_t2, c_t3 = st.columns(3)
    with c_t1:
        lost_set_1 = st.checkbox("Favorite Lost Set 1?")
    with c_t2:
        unforced_errors_high = st.checkbox("Lost due to High Unforced Errors (Not Opponent Winners)?")
    with c_t3:
        no_injury = st.checkbox("Zero Signs of Injury / Medical Timeouts?")
        
    if st.button("Validate Tennis Swing Bet"):
        st.markdown("---")
        
        cond1 = pre_odds <= -200
        cond2 = surface_win_pct >= 65.0
        cond3 = lost_set_1 and unforced_errors_high and no_injury
        
        if cond1 and cond2 and cond3:
            st.success("🟢 GREEN LIGHT: +EV Opportunity. Favorite is elite on this surface, healthy, and merely uncalibrated. Buy live line at discount.")
        else:
            st.error("🔴 RED LIGHT / PASS: Criteria not satisfied.")
            if not cond1:
                st.write("- Pre-match favorite was not heavy enough (needs <= -200).")
            if not cond2:
                st.write("- Favorite surface win rate is below 65% threshold.")
            if not cond3:
                st.write("- Check lost set status, unforced errors vs winners ratio, or injury concerns.")