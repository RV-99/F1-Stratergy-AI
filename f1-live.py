# F1 AI Strategy Companion - Live + Historical
# Run with: python -m streamlit run f1-live.py

import streamlit as st
import fastf1
import requests
import warnings
import os
import time
from datetime import datetime
warnings.filterwarnings('ignore')

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="F1 Strategy AI",
    page_icon="🏎",
    layout="wide"
)

# ── YOUR API KEY ───────────────────────────────────────────────────────────────
import os
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", "") if hasattr(st, "secrets") else os.environ.get("GROQ_API_KEY", "")

# ── CACHE SETUP ───────────────────────────────────────────────────────────────
cache_dir = 'f1_cache'
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)
fastf1.Cache.enable_cache(cache_dir)

# ── F1 KNOWLEDGE DOCUMENT ─────────────────────────────────────────────────────
F1_KNOWLEDGE = """
=== F1 RULES & TECHNICAL KNOWLEDGE (2026 SEASON) ===

RACE FLAGS:
- Green flag: Track clear, racing resumes
- Yellow flag: Hazard ahead, no overtaking, must slow down
- Double yellow: Extreme hazard, be prepared to stop
- Red flag: Session stopped immediately, drivers return to pit lane
- Blue flag: Shown to lapped drivers to let leader pass
- Black & white flag: Warning for unsportsmanlike behavior
- Black flag: Driver disqualified, must return to pits immediately
- Chequered flag: End of session/race
- Red & yellow striped flag: Slippery surface ahead

SAFETY CAR RULES:
- Safety Car (SC): Deployed for major incidents. All drivers must queue behind SC.
  No overtaking except when SC is returning to pits. Lapped cars may un-lap themselves.
- Virtual Safety Car (VSC): Minor incidents. All drivers must reduce speed by ~40%.
  Delta time shown on steering wheel. No overtaking permitted.
- Key strategy implication: Teams use SC/VSC periods to make "free" pit stops
  since gap to cars ahead is neutralised. This can completely change race outcomes.

PENALTY TYPES:
- 5-second penalty: Added to race time at next pit stop or end of race
- 10-second penalty: Added to race time at next pit stop or end of race
- Drive-through penalty: Must drive through pit lane without stopping (~20-25s lost)
- Stop-go penalty (10s): Must stop in pit box for 10 seconds
- Grid penalty: Applied to next race qualifying result (3, 5, 10, or back of grid)
- Disqualification (DSQ): Removed from results entirely
- Reprimand: Warning, 3 reprimands = 10-place grid penalty

COMMON PENALTY CAUSES:
- Forcing another driver off track
- Causing a collision
- Unsafe release from pit box
- Speeding in pit lane (>80km/h)
- Ignoring blue flags
- Track limits violations (4+ times = investigated)
- Cutting chicanes and gaining advantage
- Not following VSC delta times

DRS (Drag Reduction System) — 2026 CHANGES:
- In 2025 and before: DRS opens rear wing to reduce drag on straights
- In 2026: Active Aerodynamics (AAS) replaces DRS entirely
  - Front and rear wing can actively adjust throughout lap
  - "Z-mode" for straight-line speed (low drag)
  - "X-mode" for cornering (high downforce)
  - Available to all drivers at all times, not just within 1 second
  - Fundamentally changes overtaking dynamics

2026 REGULATION CHANGES:
- Smaller, lighter cars (768kg vs 800kg)
- New 1.6L V6 hybrid power unit with 50/50 ICE/electrical power split
- MGU-H removed, single MGU-K retained but more powerful
- Active Aerodynamics (AAS) replaces DRS
- Narrower cars for easier racing
- Pirelli continues as tire supplier
- New constructors: Cadillac (11th team, American)
- Ferrari-powered teams: Ferrari, Haas (customer), others
- Mercedes-powered: Mercedes works, McLaren (customer)
- Red Bull powertrains (RBPT): Red Bull, Racing Bulls
- Renault/Alpine: Alpine works team
- Audi: Sauber rebranded as Audi works team

TIRE COMPOUNDS (Pirelli):
- C1 (Hardest): Slowest, most durable, used at high-deg circuits
- C2: Hard compound, durable
- C3: Medium compound, balanced
- C4: Soft compound, fast but wears quickly
- C5 (Softest): Fastest, least durable, used at smooth low-deg circuits
- Pirelli nominates 3 compounds per race weekend (Hard/Medium/Soft labels)
- Intermediate: Wet weather, treaded, for damp but not fully wet conditions
- Full Wet: Heavy rain only, extreme wet weather

TIRE STRATEGY CONCEPTS:
- Undercut: Pit before rival to get fresh tires, hope to come out ahead
- Overcut: Stay out longer than rival, hope tire advantage wears off
- One-stop: Single pit stop, slower but saves time in pits
- Two-stop: Two pit stops, faster tires but 2x pit time lost
- Free pit stop: Pit during SC/VSC without losing position
- Tire bank: Teams have 13 sets of dry tires per weekend to manage

POINTS SYSTEM:
- P1: 25 points
- P2: 18 points  
- P3: 15 points
- P4: 12 points
- P5: 10 points
- P6: 8 points
- P7: 6 points
- P8: 4 points
- P9: 2 points
- P10: 1 point
- Fastest lap: 1 bonus point (if finishing in top 10)
- Sprint race: 8-7-6-5-4-3-2-1 for top 8

PIT STOP RULES:
- Minimum 4 crew members allowed over the wall
- Unsafe release: Exiting pit box into path of another car = penalty
- Pit lane speed limit: 80km/h (60km/h at some circuits)
- Must use at least 2 different dry compounds during race (if no red flag)
"""

# ── FETCH 2026 CHAMPIONSHIP STANDINGS ─────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_championship_standings():
    """Fetch current 2026 driver and constructor standings from OpenF1."""
    try:
        # get latest race results to build standings
        r = requests.get("https://api.openf1.org/v1/sessions?session_type=Race&year=2026", timeout=10)
        sessions = [s for s in r.json() if isinstance(s, dict)]
        if not sessions:
            return "Championship standings unavailable.", "Championship standings unavailable."

        # get results from all 2026 races
        driver_points = {}
        constructor_points = {}

        for session in sessions:
            sk = session.get('session_key')
            if not sk:
                continue
            try:
                pos_r = requests.get(f"https://api.openf1.org/v1/position?session_key={sk}", timeout=8)
                positions = pos_r.json()
                dr_r = requests.get(f"https://api.openf1.org/v1/drivers?session_key={sk}", timeout=8)
                drivers = {d.get('driver_number'): d for d in dr_r.json() if isinstance(d, dict)}

                points_map = {1:25,2:18,3:15,4:12,5:10,6:8,7:6,8:4,9:2,10:1}
                seen = set()
                latest_pos = {}
                for p in positions:
                    if isinstance(p, dict):
                        dn = p.get('driver_number')
                        latest_pos[dn] = p.get('position', 99)

                for dn, pos in latest_pos.items():
                    if dn in seen: continue
                    seen.add(dn)
                    pts = points_map.get(pos, 0)
                    if pts == 0: continue
                    driver = drivers.get(dn, {})
                    name = driver.get('full_name') or driver.get('last_name') or f'#{dn}'
                    team = driver.get('team_name', 'Unknown')
                    driver_points[name] = driver_points.get(name, 0) + pts
                    constructor_points[team] = constructor_points.get(team, 0) + pts
            except:
                continue

        # format standings
        driver_standing = "\n".join([f"  {i+1}. {n}: {p} pts" for i,(n,p) in enumerate(sorted(driver_points.items(), key=lambda x:-x[1])[:10])])
        constructor_standing = "\n".join([f"  {i+1}. {t}: {p} pts" for i,(t,p) in enumerate(sorted(constructor_points.items(), key=lambda x:-x[1])[:10])])

        return driver_standing or "Standings unavailable.", constructor_standing or "Standings unavailable."
    except:
        return "Standings unavailable.", "Standings unavailable."

driver_standings, constructor_standings = get_championship_standings()

SEASON_CONTEXT = f"""
=== 2026 CHAMPIONSHIP STANDINGS (CURRENT) ===

DRIVERS:
{driver_standings}

CONSTRUCTORS:
{constructor_standings}
"""

# ── CUSTOM CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.stApp { background-color: #0f0f0f; color: #f0f0f0; }

/* Dropdown styling */
div[data-baseweb="select"] * { background-color: #1a1a1a !important; color: #f0f0f0 !important; }
div[data-baseweb="popover"] * { background-color: #1a1a1a !important; color: #f0f0f0 !important; }
div[data-baseweb="menu"] { background-color: #1a1a1a !important; }
div[data-baseweb="menu"] li { background-color: #1a1a1a !important; color: #f0f0f0 !important; }
div[data-baseweb="menu"] li:hover { background-color: #2a2a2a !important; }
div[data-baseweb="option"] { background-color: #1a1a1a !important; color: #f0f0f0 !important; }
div[data-baseweb="option"]:hover { background-color: #e10600 !important; }
[data-testid="stSelectbox"] div { background-color: #1a1a1a !important; color: #f0f0f0 !important; border-color: #444 !important; }
[data-testid="stExpander"] { background-color: #1a1a1a !important; border: 1px solid #333 !important; border-radius: 8px !important; }
[data-testid="stExpander"] pre { background-color: #1a1a1a !important; color: #dddddd !important; }
[data-testid="stExpander"] code { background-color: #1a1a1a !important; color: #dddddd !important; }
p, li, ul, ol, span { color: #dddddd !important; }
.stMarkdown p, .stMarkdown li, .stMarkdown ol, .stMarkdown ul { color: #dddddd !important; }
[data-testid="stSidebar"] { background-color: #1a1a1a; border-right: 2px solid #e10600; }
[data-testid="stSidebar"] h1 { color: #e10600; font-weight: 800; }
h1 { color: #ffffff !important; font-weight: 900 !important; text-transform: uppercase; }
h2, h3 { color: #ffffff !important; border-left: 4px solid #e10600; padding-left: 12px; }
.stButton > button {
    background-color: #e10600 !important; color: white !important;
    border: none !important; font-weight: 700 !important;
    text-transform: uppercase !important; border-radius: 4px !important;
}
.stButton > button:hover { background-color: #ff1a0e !important; }
[data-testid="stChatMessage"] {
    background-color: #1e1e1e !important;
    border-radius: 8px !important; border: 1px solid #2a2a2a !important;
}
[data-testid="stInfo"] { background-color: #1a1a1a !important; border-left: 4px solid #e10600 !important; }
hr { border-color: #333 !important; }
p { color: #dddddd !important; }
label { color: #aaaaaa !important; font-size: 0.8rem !important; text-transform: uppercase !important; }

.live-badge {
    display: inline-flex; align-items: center; gap: 8px;
    background: #1a0000; border: 1px solid #e10600;
    border-radius: 20px; padding: 4px 14px;
    color: #e10600; font-weight: 700; font-size: 0.85rem;
    letter-spacing: 1px;
}
.live-dot {
    width: 8px; height: 8px; background: #e10600;
    border-radius: 50%; animation: pulse 1s infinite;
}
@keyframes pulse {
    0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; }
}
.driver-card {
    background: #1a1a1a; border: 1px solid #2a2a2a;
    border-radius: 8px; padding: 12px 16px; margin-bottom: 8px;
}
.driver-card:hover { border-color: #e10600; }
.pos { color: #e10600; font-weight: 900; font-size: 1.2rem; min-width: 30px; }
.driver-name { color: white; font-weight: 600; }
.driver-team { color: #888; font-size: 0.8rem; }
.tire-soft { color: #ff4444; font-weight: 700; }
.tire-medium { color: #ffdd00; font-weight: 700; }
.tire-hard { color: #ffffff; font-weight: 700; }
.tire-inter { color: #44ff44; font-weight: 700; }
.tire-wet { color: #4444ff; font-weight: 700; }
</style>
""", unsafe_allow_html=True)


# ── HELPER FUNCTIONS ──────────────────────────────────────────────────────────
def ask_groq(messages, max_tokens=800):
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": "llama-3.3-70b-versatile", "messages": messages, "max_tokens": max_tokens, "temperature": 0.7}
    )
    result = response.json()
    if "choices" in result:
        return result["choices"][0]["message"]["content"]
    return f"AI Error: {result}"


def get_race_control_messages(session_key):
    """Fetch safety car, VSC, flags and penalties from OpenF1 race control."""
    try:
        r = requests.get(f"https://api.openf1.org/v1/race_control?session_key={session_key}", timeout=10)
        messages = [m for m in r.json() if isinstance(m, dict)]
        if not messages:
            return ""

        important = []
        for msg in messages:
            category = msg.get('category', '')
            flag     = msg.get('flag', '')
            message  = msg.get('message', '')
            lap      = msg.get('lap_number', '?')

            if any(x in category.upper() for x in ['SAFETY CAR', 'VSC', 'FLAG', 'PENALTY', 'DECISION']):
                important.append(f"Lap {lap}: [{category}] {flag} {message}".strip())
            elif any(x in str(message).upper() for x in ['SAFETY CAR', 'VSC', 'PENALTY', 'DRIVE THROUGH', 'STOP GO', 'BLACK', 'RED FLAG']):
                important.append(f"Lap {lap}: {message}")

        if not important:
            return ""
        return "\n".join(important[:30])  # cap at 30 messages
    except:
        return ""


def get_tire_color(compound):
    colors = {'SOFT': 'tire-soft', 'MEDIUM': 'tire-medium', 'HARD': 'tire-hard',
              'INTERMEDIATE': 'tire-inter', 'WET': 'tire-wet'}
    return colors.get(str(compound).upper(), 'driver-team')


def fetch_live_data():
    """Fetch current live session data from OpenF1."""
    try:
        # get the latest session
        r = requests.get("https://api.openf1.org/v1/sessions?session_key=latest", timeout=10)
        sessions = r.json()
        if not sessions:
            return None, None, None, None
        session = sessions[-1] if isinstance(sessions, list) else sessions

        session_key  = session.get('session_key')
        session_name = (session.get('session_name') or session.get('session_type') or 'Race')
        meeting_name = (session.get('meeting_name') or session.get('location') or session.get('circuit_short_name') or f"Round {session.get('meeting_key','?')}")
        date_str = str(session.get('date_start') or '')
        year_str = date_str[:4] if len(date_str) >= 4 else ''
        if year_str and year_str not in meeting_name:
            meeting_name = f"{meeting_name} {year_str}"

        # get drivers
        dr = requests.get(f"https://api.openf1.org/v1/drivers?session_key={session_key}", timeout=10)
        drivers = {d['driver_number']: d for d in dr.json() if isinstance(d, dict)}

        # get latest position for each driver
        pos_r = requests.get(f"https://api.openf1.org/v1/position?session_key={session_key}", timeout=10)
        positions_raw = pos_r.json()
        # get most recent position per driver
        positions = {}
        for p in positions_raw:
            if isinstance(p, dict):
                dn = p.get('driver_number')
                positions[dn] = p

        # get pit stops
        pit_r = requests.get(f"https://api.openf1.org/v1/pit?session_key={session_key}", timeout=10)
        pits_raw = pit_r.json()
        pits = {}
        for p in pits_raw:
            if isinstance(p, dict):
                dn = p.get('driver_number')
                if dn not in pits:
                    pits[dn] = []
                pits[dn].append(p)

        # get latest stints (tire data)
        stint_r = requests.get(f"https://api.openf1.org/v1/stints?session_key={session_key}", timeout=10)
        stints_raw = stint_r.json()
        current_stints = {}
        for s in stints_raw:
            if isinstance(s, dict):
                dn = s.get('driver_number')
                current_stints[dn] = s  # last entry = current stint

        # get latest lap number
        lap_r = requests.get(f"https://api.openf1.org/v1/laps?session_key={session_key}&driver_number=1", timeout=10)
        laps_raw = lap_r.json()
        current_lap = max([l.get('lap_number', 0) for l in laps_raw if isinstance(l, dict)], default=0)

        return session, drivers, positions, pits, current_stints, current_lap, meeting_name, session_name

    except Exception as e:
        return None, None, None, None, None, 0, "Error", str(e)


@st.cache_data(ttl=3600)  # cache for 1 hour only
def get_schedule(year, session_type="Race"):
    """Get race calendar — OpenF1 for 2026+, FastF1 for 2018-2025."""
    import pandas as pd
    if year >= 2026:
        # try exact session type first, then fallback to all sessions
        r = requests.get(f"https://api.openf1.org/v1/sessions?year={year}", timeout=15)
        try:
            all_sessions = [s for s in r.json() if isinstance(s, dict)]
        except:
            return pd.DataFrame()

        # filter by session type — try multiple name variants
        type_variants = {
            "Race":              ["Race", "Grand Prix"],
            "Qualifying":        ["Qualifying", "Shootout"],
            "Sprint Race":       ["Sprint Race", "Sprint"],
            "Sprint Qualifying": ["Sprint Qualifying", "Sprint Shootout"],
            "Practice 1":        ["Practice 1", "FP1", "Free Practice 1"],
            "Practice 2":        ["Practice 2", "FP2", "Free Practice 2"],
            "Practice 3":        ["Practice 3", "FP3", "Free Practice 3"],
        }
        variants = type_variants.get(session_type, [session_type])

        def matches_session(s):
            name = (s.get("session_name") or s.get("session_type") or "").lower()
            stype = (s.get("session_type") or "").lower()
            # for Race: match "race" but NOT "sprint race"
            if session_type == "Race":
                return ("race" in name or "grand prix" in name) and "sprint" not in name
            return any(v.lower() in name or v.lower() in stype for v in variants)

        sessions = [s for s in all_sessions if matches_session(s)]

        # if still empty, show all sessions as fallback
        if not sessions:
            sessions = all_sessions

        # if nothing found with filter, return empty
        if not sessions:
            return pd.DataFrame()

        # deduplicate by meeting name — keep first occurrence
        rows = []
        seen = set()
        for s in sessions:
            name = (s.get('meeting_name') or s.get('location') or 'Unknown')
            if name not in seen:
                seen.add(name)
                rows.append({
                    'EventName':   name,
                    'RoundNumber': len(rows) + 1,
                    'session_key': s.get('session_key'),
                    'EventFormat': 'conventional',
                    'date_start':  s.get('date_start', '')
                })
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    else:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        return schedule[schedule['EventFormat'] != 'testing']


# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown("<span style='color:#e10600;font-size:0.8rem;font-weight:700;letter-spacing:3px'>POWERED BY FASTF1 + AI</span>", unsafe_allow_html=True)
st.title("🏎 F1 Strategy AI")
st.markdown("<p style='color:#888;margin-top:-10px'>Real race data. Real strategy insights.</p>", unsafe_allow_html=True)


# ── TABS ──────────────────────────────────────────────────────────────────────
tab_live, tab_history, tab_tires = st.tabs(["🔴 LIVE RACE", "📚 HISTORICAL RACES", "📊 TIRE ANALYTICS"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: LIVE RACE
# ══════════════════════════════════════════════════════════════════════════════
with tab_live:

    st.markdown("<div class='live-badge'><div class='live-dot'></div>LIVE TIMING</div>", unsafe_allow_html=True)
    st.markdown("")

    col_refresh, col_auto = st.columns([1, 3])
    with col_refresh:
        refresh_btn = st.button("🔄 Refresh Data", use_container_width=True)
    with col_auto:
        auto_refresh = st.toggle("Auto-refresh every 30s", value=False)

    st.divider()

    # fetch live data
    if refresh_btn or auto_refresh or 'live_loaded' not in st.session_state:
        with st.spinner("Fetching live race data..."):
            result = fetch_live_data()
            if result[0] is not None:
                session, drivers, positions, pits, stints, current_lap, meeting, session_name = result
                st.session_state.live_session    = session
                st.session_state.live_drivers    = drivers
                st.session_state.live_positions  = positions
                st.session_state.live_pits       = pits
                st.session_state.live_stints     = stints
                st.session_state.live_lap        = current_lap
                st.session_state.live_meeting    = meeting
                st.session_state.live_session_name = session_name
                st.session_state.live_loaded     = True
                st.session_state.live_updated    = datetime.now().strftime("%H:%M:%S")
            else:
                st.session_state.live_loaded = False

    if st.session_state.get('live_loaded'):
        drivers   = st.session_state.live_drivers
        positions = st.session_state.live_positions
        pits      = st.session_state.live_pits
        stints    = st.session_state.live_stints
        current_lap = st.session_state.live_lap
        meeting   = st.session_state.live_meeting
        session_name = st.session_state.live_session_name

        st.markdown(f"<h2>📍 {meeting} — {session_name}</h2>", unsafe_allow_html=True)
        st.markdown(f"<p style='color:#666'>Last updated: {st.session_state.get('live_updated', 'N/A')} · Lap {current_lap}</p>", unsafe_allow_html=True)

        # sort drivers by position
        sorted_drivers = sorted(
            positions.items(),
            key=lambda x: x[1].get('position', 99)
        )

        # build race snapshot for AI
        snapshot_lines = []
        st.markdown("### 🏁 Live Race Order")

        for driver_num, pos_data in sorted_drivers:
            pos        = pos_data.get('position', '?')
            driver     = drivers.get(driver_num, {})
            name       = driver.get('full_name') or driver.get('last_name') or f'#{driver_num}'
            team       = driver.get('team_name', '')
            abbr       = driver.get('name_acronym', str(driver_num))

            # tire info
            stint      = stints.get(driver_num, {})
            compound   = stint.get('compound', 'Unknown')
            tire_age   = stint.get('lap_start', 0)
            tire_laps  = max(0, current_lap - tire_age) if (tire_age and current_lap > 0) else current_lap if tire_age == 0 else '?'

            # pit count
            driver_pits = pits.get(driver_num, [])
            pit_count   = len(driver_pits)

            tire_class  = get_tire_color(compound)
            compound_short = compound[:1] if compound != 'Unknown' else '?'

            st.markdown(f"""
            <div class='driver-card'>
                <span class='pos'>P{pos}</span>
                <span class='driver-name'> {abbr} — {name}</span>
                <span class='driver-team'> · {team}</span>
                <span class='{tire_class}' style='float:right'>
                    {compound_short} · {tire_laps} laps · {pit_count} stops
                </span>
            </div>
            """, unsafe_allow_html=True)

            snapshot_lines.append(
                f"P{pos} #{abbr} {name} ({team}) — {compound} tires age {tire_laps} laps, {pit_count} pit stops"
            )

        race_snapshot = "\n".join(snapshot_lines)

        # AI live analysis
        st.divider()
        st.markdown("### 🤖 AI Strategy Advice")

        if st.button("⚡ Get Live Strategy Advice", use_container_width=False):
            with st.spinner("Analysing live race situation..."):
                live_prompt = f"""Current race: {meeting} — {session_name}
Lap: {current_lap}

Live race order:
{race_snapshot}

Give urgent, actionable strategy advice:
1. Who should pit in the next 3 laps and why?
2. Who is most vulnerable to an undercut right now?
3. One key strategic call each top-3 team should make immediately."""

                messages = [
                    {"role": "system", "content": f"You are a live F1 race strategist giving real-time advice during a race. Be urgent, specific, and direct. Use driver names and explain tire age implications clearly.\n\n{F1_KNOWLEDGE}\n\n{SEASON_CONTEXT}"},
                    {"role": "user",   "content": live_prompt}
                ]
                advice = ask_groq(messages, max_tokens=600)
                st.markdown(f"""
                <div style='background:#1a0000;border:1px solid #e10600;border-radius:8px;padding:20px;margin-top:16px'>
                    <div style='color:#e10600;font-weight:700;margin-bottom:12px;font-size:0.85rem;letter-spacing:1px'>⚡ LIVE STRATEGY BRIEF</div>
                    <div style='color:#f0f0f0;line-height:1.7'>{advice}</div>
                </div>
                """, unsafe_allow_html=True)

        # live chat
        st.divider()
        st.markdown("### 💬 Ask about the live race")

        if 'live_messages' not in st.session_state:
            st.session_state.live_messages = []

        for msg in st.session_state.live_messages:
            with st.chat_message(msg["role"], avatar="🏎" if msg["role"] == "assistant" else "👤"):
                st.markdown(msg["content"])

        live_input = st.chat_input("Ask anything about the current race...")
        if live_input:
            context = f"Live race: {meeting}, Lap {current_lap}\n{race_snapshot}"
            full_q  = f"{context}\n\nQuestion: {live_input}"

            st.session_state.live_messages.append({"role": "user", "content": live_input})
            with st.chat_message("user", avatar="👤"):
                st.markdown(live_input)

            msgs = [
                {"role": "system", "content": "You are a live F1 race strategist. Answer questions about the current race using the provided live data."},
                {"role": "user",   "content": full_q}
            ]
            with st.chat_message("assistant", avatar="🏎"):
                with st.spinner("Thinking..."):
                    response = ask_groq(msgs, max_tokens=400)
                    st.session_state.live_messages.append({"role": "assistant", "content": response})
                    st.markdown(response)

        # auto refresh
        if auto_refresh:
            time.sleep(30)
            st.rerun()

    else:
        st.markdown("""
        <div style='text-align:center;padding:60px 20px'>
            <div style='font-size:3rem'>📡</div>
            <h3 style='color:white;border:none;padding:0'>No live session detected</h3>
            <p style='color:#888'>Live data is only available during race weekends.<br>
            The next race is the <strong style='color:#e10600'>Canadian Grand Prix</strong> — check back on race day!</p>
            <p style='color:#555;font-size:0.85rem'>Use the Historical Races tab to analyse any past race.</p>
        </div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: HISTORICAL RACES
# ══════════════════════════════════════════════════════════════════════════════
with tab_history:

    st.sidebar.title("📚 Historical Race")
    year = st.sidebar.selectbox("Season", options=list(range(2026, 2017, -1)), index=0)

    # ── SESSION TYPE FIRST — drives what appears in the race list ─────────────
    session_type = st.sidebar.selectbox("Session Type", options=[
        ("🏁 Race",              "Race",             "R"),
        ("⏱ Qualifying",         "Qualifying",       "Q"),
        ("🏃 Sprint",             "Sprint Race",      "S"),
        ("⏱ Sprint Shootout",    "Sprint Qualifying","SQ"),
        ("🔧 Practice 1",        "Practice 1",       "FP1"),
        ("🔧 Practice 2",        "Practice 2",       "FP2"),
        ("🔧 Practice 3",        "Practice 3",       "FP3"),
    ], format_func=lambda x: x[0])

    session_label    = session_type[0]
    session_openf1   = session_type[1]
    session_fastf1   = session_type[2]

    # ── LOAD CALENDAR FILTERED BY SESSION TYPE ────────────────────────────────
    with st.sidebar:
        with st.spinner(f"Loading {year} {session_label} calendar..."):
            try:
                if year >= 2026:
                    # for 2026+ fetch only sessions of the selected type
                    races      = get_schedule(year, session_openf1)
                else:
                    # for FastF1 years always load the full race calendar
                    # (FastF1 schedule doesn't filter by session type at calendar level)
                    races      = get_schedule(year, "Race")
                
                if races is None or len(races) == 0:
                    st.warning(f"No {session_label} sessions found for {year}.")
                    race_names = []
                else:
                    race_names = races['EventName'].tolist()
            except Exception as e:
                st.error(f"Could not load calendar: {e}")
                race_names = []

    if not race_names:
        st.sidebar.warning("No sessions available. Try a different year or session type.")
        selected_race = None
    else:
        selected_race = st.sidebar.selectbox("Race Weekend", options=race_names)

    load_button = st.sidebar.button("🔍 Analyse Session", use_container_width=True, disabled=not race_names)
    st.sidebar.divider()
    st.sidebar.markdown("<p style='color:#555;font-size:0.75rem'>Built with FastF1 · Groq · Streamlit</p>", unsafe_allow_html=True)

    if 'hist_messages'    not in st.session_state: st.session_state.hist_messages    = []
    if 'hist_race_loaded' not in st.session_state: st.session_state.hist_race_loaded = False
    if 'hist_summary'     not in st.session_state: st.session_state.hist_summary     = ""
    if 'hist_label'       not in st.session_state: st.session_state.hist_label       = ""
    if 'hist_weather'     not in st.session_state: st.session_state.hist_weather     = ""

    def build_summary_from_openf1(session_key, race_label):
        """Build rich race summary from OpenF1 API for 2026+ races."""
        dr_r    = requests.get(f"https://api.openf1.org/v1/drivers?session_key={session_key}", timeout=10)
        pit_r   = requests.get(f"https://api.openf1.org/v1/pit?session_key={session_key}", timeout=10)
        stint_r = requests.get(f"https://api.openf1.org/v1/stints?session_key={session_key}", timeout=10)
        pos_r   = requests.get(f"https://api.openf1.org/v1/position?session_key={session_key}", timeout=10)
        lap_r   = requests.get(f"https://api.openf1.org/v1/laps?session_key={session_key}", timeout=10)
        weather_r = requests.get(f"https://api.openf1.org/v1/weather?session_key={session_key}", timeout=10)

        drivers  = [d for d in dr_r.json() if isinstance(d, dict)]
        pits_raw = [p for p in pit_r.json() if isinstance(p, dict)]
        stints_raw = [s for s in stint_r.json() if isinstance(s, dict)]
        positions_raw = [p for p in pos_r.json() if isinstance(p, dict)]
        laps_raw = [l for l in lap_r.json() if isinstance(l, dict)]

        # weather
        weather_raw = [w for w in weather_r.json() if isinstance(w, dict)]
        if weather_raw:
            avg_temp  = round(sum(w.get('air_temperature',0) for w in weather_raw) / len(weather_raw), 1)
            avg_track = round(sum(w.get('track_temperature',0) for w in weather_raw) / len(weather_raw), 1)
            rainfall  = any(w.get('rainfall', False) for w in weather_raw)
            weather_str = f"Air: {avg_temp}°C · Track: {avg_track}°C · Rain: {'Yes ☔' if rainfall else 'No ☀️'}"
        else:
            weather_str = "Weather data unavailable"

        # group data by driver
        pits_by_driver   = {}
        for p in pits_raw:
            pits_by_driver.setdefault(p.get('driver_number'), []).append(p)

        stints_by_driver = {}
        for s in stints_raw:
            stints_by_driver.setdefault(s.get('driver_number'), []).append(s)

        # final position per driver (last position entry)
        final_pos = {}
        for p in positions_raw:
            dn = p.get('driver_number')
            final_pos[dn] = p.get('position', 99)

        # total laps per driver (to detect DNF)
        max_lap_overall = max((l.get('lap_number', 0) for l in laps_raw), default=0)
        laps_by_driver  = {}
        for l in laps_raw:
            dn = l.get('driver_number')
            laps_by_driver[dn] = max(laps_by_driver.get(dn, 0), l.get('lap_number', 0))

        # fastest lap
        fastest_time = None
        fastest_driver = None
        for l in laps_raw:
            lt = l.get('lap_duration')
            if lt and (fastest_time is None or lt < fastest_time):
                fastest_time   = lt
                fastest_driver = l.get('driver_number')

        lines = []
        for d in sorted(drivers, key=lambda x: final_pos.get(x.get('driver_number'), 99)):
            dn    = d.get('driver_number')
            name  = d.get('full_name') or d.get('last_name') or f'#{dn}'
            team  = d.get('team_name', 'Unknown')
            abbr  = d.get('name_acronym', str(dn))
            pos   = final_pos.get(dn, '?')

            # pit laps
            driver_pits = sorted(pits_by_driver.get(dn, []), key=lambda x: x.get('lap_number', 0))
            pit_laps    = [str(p.get('lap_number','?')) for p in driver_pits]

            # tire stints with lap ranges
            driver_stints = sorted(stints_by_driver.get(dn, []), key=lambda x: x.get('lap_start', 0))
            compound_info = []
            for s in driver_stints:
                comp      = s.get('compound', '?')
                lap_start = s.get('lap_start', '?')
                lap_end   = s.get('lap_end', '?')
                compound_info.append(f"{comp}({lap_start}-{lap_end})")

            # DNF detection — driver must complete less than 90% of leader laps
            driver_max_lap = laps_by_driver.get(dn, 0)
            dnf_threshold  = max_lap_overall * 0.90
            is_dnf = (driver_max_lap < dnf_threshold) and max_lap_overall > 3 and driver_max_lap > 0
            dnf_note = f" ⚠️ DNF on lap {driver_max_lap}" if is_dnf else ""

            # fastest lap flag
            fl_flag = " 🟣 FASTEST LAP" if dn == fastest_driver else ""

            pit_info  = f"pits: laps {', '.join(pit_laps)}" if pit_laps else "no pit stops"
            comp_str  = f"stints: {' → '.join(compound_info)}" if compound_info else ""

            line = f"{abbr} {name} ({team}) — P{pos}{dnf_note}, {pit_info}"
            if comp_str:  line += f", {comp_str}"
            if fl_flag:   line += fl_flag
            lines.append(line)

        return "\n".join(lines), weather_str

    def load_race_data(year, race_name, ff1_type='R'):
        races     = get_schedule(year)
        event     = races[races['EventName'] == race_name].iloc[0]
        round_num = event['RoundNumber']
        session   = fastf1.get_session(year, round_num, ff1_type)
        session.load(telemetry=False, weather=True, messages=True)
        return session

    if load_button and selected_race:
        st.session_state.hist_messages    = []
        st.session_state.hist_race_loaded = False

        with st.spinner(f"⏳ Loading {selected_race} {year} — {session_label}..."):
            try:
                # ── 2026+ uses OpenF1 directly ────────────────────────────
                if year >= 2026:
                    races_df2   = races  # already loaded above, same session type
                    event       = races_df2[races_df2['EventName'] == selected_race].iloc[0]
                    session_key = event.get('session_key')
                    race_label  = f"{selected_race} {year}"
                    race_summary, weather_str = build_summary_from_openf1(session_key, race_label)

                    st.session_state.hist_summary     = race_summary
                    st.session_state.hist_label       = race_label
                    st.session_state.hist_weather     = weather_str
                    st.session_state.hist_race_loaded = True

                    system_prompt = """You are an expert F1 race strategist and commentator with deep knowledge of tire strategy, DNFs, incidents, undercuts, and race craft. When you see DNF next to a driver's name, always explain what their retirement means strategically."""
                    initial_msg = f"""Race: {race_label}
Weather: {weather_str}

Full race data (position, DNF reasons, tire stints with lap ranges, pit stop laps):
{race_summary}

Give a detailed strategic analysis:
1. **Best strategy** — which team/driver executed perfectly and why
2. **Worst strategy** — who made the wrong calls
3. **Key moment** — the single decision that decided the race
4. **DNFs and incidents** — explain any retirements and their strategic impact
5. **Biggest mover** — who gained the most positions"""

                    st.session_state.hist_messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": initial_msg}
                    ]
                    with st.spinner("🤖 Analysing strategy..."):
                        ai_resp = ask_groq(st.session_state.hist_messages)
                        st.session_state.hist_messages.append({"role": "assistant", "content": ai_resp})
                    st.rerun()

                # ── 2018-2025 uses FastF1 ─────────────────────────────────
                else:
                    session      = load_race_data(year, selected_race, session_fastf1)
                    results      = session.results
                    laps         = session.laps
                    weather_data = session.weather_data

                    if weather_data is not None and len(weather_data) > 0:
                        avg_temp  = round(weather_data['AirTemp'].mean(), 1)
                        avg_track = round(weather_data['TrackTemp'].mean(), 1)
                        rainfall  = weather_data['Rainfall'].any()
                        weather_str = f"Air: {avg_temp}°C · Track: {avg_track}°C · Rain: {'Yes ☔' if rainfall else 'No ☀️'}"
                    else:
                        weather_str = "Weather data unavailable"

                # find fastest lap holder
                try:
                    fl_driver = laps.pick_fastest()['Driver']
                except:
                    fl_driver = None

                driver_lines = []
                for _, driver in results.iterrows():
                    abbr     = driver.get('Abbreviation', '?')
                    name     = f"{driver.get('FirstName','')} {driver.get('LastName','')}".strip()
                    team     = driver.get('TeamName', 'Unknown')
                    position = driver.get('Position', '?')
                    status   = driver.get('Status', 'Unknown')
                    grid_pos = driver.get('GridPosition', '?')
                    points   = driver.get('Points', 0)

                    driver_laps = laps[laps['Driver'] == abbr]

                    # pit stop laps
                    try:
                        pit_laps = [int(l) for l in driver_laps[driver_laps['PitOutTime'].notna()]['LapNumber'].tolist()]
                    except:
                        pit_laps = []

                    # tire compounds used in order
                    try:
                        compounds = []
                        for stint_num in sorted(driver_laps['Stint'].dropna().unique()):
                            stint_laps = driver_laps[driver_laps['Stint'] == stint_num]
                            comp = stint_laps['Compound'].dropna().iloc[0] if len(stint_laps) > 0 else None
                            if comp and str(comp) != 'nan':
                                lap_start = int(stint_laps['LapNumber'].min())
                                lap_end   = int(stint_laps['LapNumber'].max())
                                compounds.append(f"{comp}({lap_start}-{lap_end})")
                    except:
                        try:
                            compounds = [c for c in driver_laps['Compound'].dropna().unique().tolist() if c and str(c) != 'nan']
                        except:
                            compounds = []

                    # retirement lap if DNF
                    dnf_lap = ''
                    finished_statuses = ['Finished', '+1 Lap', '+2 Laps', '+3 Laps', '+4 Laps', '+5 Laps']
                    is_dnf = str(status) not in finished_statuses
                    if is_dnf:
                        try:
                            last_lap = int(driver_laps['LapNumber'].max())
                            dnf_lap  = f" on lap {last_lap}"
                        except:
                            dnf_lap = ''

                    # fastest lap flag
                    fl_flag = ' 🟣 FASTEST LAP' if abbr == fl_driver else ''

                    # grid vs finish (positions gained/lost)
                    try:
                        pos_int  = int(position)
                        grid_int = int(grid_pos)
                        delta    = grid_int - pos_int
                        pos_delta = f" (+{delta} pos)" if delta > 0 else (f" ({delta} pos)" if delta < 0 else " (same grid)")
                    except:
                        pos_delta = ''

                    # build the line
                    if is_dnf:
                        status_info = f"DNF — {status}{dnf_lap}"
                    else:
                        try:
                            status_info = f"P{int(position)}{pos_delta}"
                        except:
                            status_info = str(status)

                    pit_info      = f"pits: laps {pit_laps}" if pit_laps else "no pit stops"
                    compound_info = f"stints: {' → '.join(compounds)}" if compounds else ""

                    line = f"{abbr} {name} ({team}) — {status_info}, started P{grid_pos}, {pit_info}"
                    if compound_info: line += f", {compound_info}"
                    if fl_flag:       line += fl_flag
                    driver_lines.append(line)

                race_summary = "\n".join(driver_lines)
                race_label   = f"{selected_race} {year}"

                st.session_state.hist_summary     = race_summary
                st.session_state.hist_label       = race_label
                st.session_state.hist_weather     = weather_str
                st.session_state.hist_race_loaded = True

                # adapt prompt based on session type
                if "Qualifying" in session_label or "Q" in session_fastf1:
                    analysis_prompt = f"""Qualifying session: {race_label}
Weather: {weather_str}

Qualifying data:
{race_summary}

Analyse this qualifying session:
1. **Pole lap** — what made the pole position lap special?
2. **Biggest surprise** — who over or underperformed vs expectations?
3. **Tire strategy** — which compound choices were interesting in Q2/Q3?
4. **Race implications** — how does this grid order set up the race strategy?
5. **Key battles** — who narrowly missed out and why?"""
                elif "Sprint" in session_label:
                    analysis_prompt = f"""Sprint session: {race_label}
Weather: {weather_str}

Sprint data:
{race_summary}

Analyse this sprint:
1. **Best sprint strategy** — who managed tires and position perfectly?
2. **Key overtakes** — which position changes were most significant?
3. **DNFs and incidents** — explain any retirements and their impact
4. **Race weekend implications** — how does this affect the main race strategy?"""
                elif "Practice" in session_label:
                    analysis_prompt = f"""Practice session: {race_label}
Weather: {weather_str}

Practice data:
{race_summary}

Analyse this practice session:
1. **Pace leaders** — who looks fastest and why?
2. **Tire data gathered** — what did teams learn about compounds?
3. **Setup concerns** — who seems to be struggling?
4. **Race predictions** — based on practice, who looks strong for the race?"""
                else:
                    analysis_prompt = f"""Race: {race_label}
Weather: {weather_str}

Full race data (finishing position, grid position, DNF reasons, tire stints with lap ranges, pit stop laps):
{race_summary}

Give a detailed strategic analysis:
1. **Best strategy** — which team/driver executed perfectly and why
2. **Worst strategy** — who made the wrong calls and what they should have done
3. **Key moment** — the single strategic decision that decided the race outcome
4. **DNFs and incidents** — for any driver marked DNF, explain what happened and how it affected the race
5. **Biggest mover** — who gained the most positions from grid to finish and how"""

                # fetch race control messages for this session
                rc_messages = ""
                if year >= 2026 and 'session_key' in dir():
                    rc_messages = get_race_control_messages(session_key)
                elif year < 2026:
                    try:
                        ff1_session_key = session.session_info.get('Key', '') if hasattr(session, 'session_info') else ''
                        if ff1_session_key:
                            rc_messages = get_race_control_messages(ff1_session_key)
                    except:
                        pass

                rc_context = f"\n\nRACE CONTROL MESSAGES (Safety Cars, Flags, Penalties):\n{rc_messages}" if rc_messages else ""

                system_prompt = f"""You are an expert F1 race strategist and commentator with access to comprehensive F1 knowledge.

{F1_KNOWLEDGE}

{SEASON_CONTEXT}

Use this knowledge to give highly accurate, technically detailed analysis. When you see DNF next to a driver's name, explain what their retirement means strategically. Be specific about driver names, lap numbers, tire choices, and reference the rules where relevant."""

                # append race control messages to the analysis
                if rc_context:
                    analysis_prompt += rc_context
                initial_msg = analysis_prompt

                st.session_state.hist_messages = [
                    {"role": "system",    "content": system_prompt},
                    {"role": "user",      "content": initial_msg}
                ]
                with st.spinner("🤖 Analysing strategy..."):
                    ai_resp = ask_groq(st.session_state.hist_messages)
                    st.session_state.hist_messages.append({"role": "assistant", "content": ai_resp})

            except Exception as e:
                st.error(f"Error: {e}")

    if st.session_state.hist_race_loaded:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(f"<h2>📍 {st.session_state.hist_label}</h2>", unsafe_allow_html=True)
        with col2:
            st.info(f"🌤 {st.session_state.hist_weather}")

        with st.expander("📊 Raw race data", expanded=False):
            st.code(st.session_state.hist_summary, language=None)

        st.divider()

        for msg in st.session_state.hist_messages:
            if msg["role"] == "system": continue
            # hide the raw data dump — only show clean user questions
            if msg["role"] == "user" and any(x in msg["content"] for x in ["Driver data:", "Full race data", "Weather:", "Give a detailed", "Analyse:"]):
                continue
            with st.chat_message(msg["role"], avatar="🏎" if msg["role"] == "assistant" else "👤"):
                st.markdown(msg["content"])

        st.divider()
        user_input = st.chat_input("Ask anything about this race strategy...")
        if user_input:
            st.session_state.hist_messages.append({"role": "user", "content": user_input})
            with st.chat_message("user", avatar="👤"):
                st.markdown(user_input)
            with st.chat_message("assistant", avatar="🏎"):
                with st.spinner("Thinking..."):
                    resp = ask_groq(st.session_state.hist_messages)
                    st.session_state.hist_messages.append({"role": "assistant", "content": resp})
                    st.markdown(resp)
    else:
        st.markdown("""
        <div style='text-align:center;padding:60px 20px'>
            <div style='font-size:3rem'>📚</div>
            <h3 style='color:white;border:none;padding:0'>Pick a race from the sidebar</h3>
            <p style='color:#888'>Analyse any race from 2018–2025 with full telemetry data.</p>
            <p style='color:#555'>Try: Abu Dhabi 2021 · Monaco 2024 · Belgian GP 2023</p>
        </div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: TIRE ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════
with tab_tires:

    st.markdown("### 📊 Tire Degradation Analysis")
    st.markdown("<p style='color:#888'>Real lap-by-lap data from 2018–2024 races. See how each compound actually degrades at each circuit.</p>", unsafe_allow_html=True)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        tire_circuit = st.selectbox("Circuit", options=[
            "Austria", "Monaco", "Silverstone", "Spa", "Monza",
            "Singapore", "Suzuka", "Bahrain", "Hungary", "Barcelona"
        ])
    with col_b:
        tire_compound = st.selectbox("Compound", options=["SOFT", "MEDIUM", "HARD"])
    with col_c:
        tire_years = st.multiselect("Years", options=[2021, 2022, 2023, 2024], default=[2022, 2023, 2024])

    analyse_tires_btn = st.button("📈 Analyse Degradation", use_container_width=False)

    @st.cache_data(ttl=86400, show_spinner=False)  # cache for 24 hours
    def get_degradation_data(circuit, compound, years):
        """Pull lap data across multiple years and build a degradation curve."""
        import pandas as pd
        all_laps = []

        for year in years:
            try:
                session = fastf1.get_session(year, circuit, 'R')
                session.load(telemetry=False, weather=False, messages=False)
                laps = session.laps

                filtered = laps[
                    (laps['Compound'] == compound) &
                    (laps['LapTime'].notna()) &
                    (laps['PitOutTime'].isna()) &
                    (laps['PitInTime'].isna()) &
                    (laps['TyreLife'].notna())
                ].copy()

                filtered['LapTimeSeconds'] = filtered['LapTime'].dt.total_seconds()
                filtered['Year'] = year
                all_laps.append(filtered[['Year', 'Driver', 'TyreLife', 'LapTimeSeconds']])
            except Exception:
                continue

        if not all_laps:
            return None, None

        combined = pd.concat(all_laps, ignore_index=True)
        if len(combined) == 0:
            return None, None

        median_time = combined['LapTimeSeconds'].median()
        clean = combined[combined['LapTimeSeconds'] < median_time * 1.15].copy()

        degradation = clean.groupby('TyreLife')['LapTimeSeconds'].agg(['mean', 'std', 'count']).reset_index()
        degradation = degradation[degradation['count'] >= 2]

        return degradation, len(clean)

    if analyse_tires_btn and tire_years:
        with st.spinner(f"Analysing {tire_compound} tire data at {tire_circuit} ({', '.join(map(str,tire_years))})... this may take a minute on first load"):
            degradation, sample_size = get_degradation_data(tire_circuit, tire_compound, tuple(tire_years))

        if degradation is None or len(degradation) < 3:
            st.warning(f"Not enough {tire_compound} tire data found for {tire_circuit} in the selected years. Try different years or a different compound.")
        else:
            st.session_state.tire_degradation = degradation
            st.session_state.tire_sample_size = sample_size
            st.session_state.tire_circuit_label = f"{tire_circuit} — {tire_compound} compound ({', '.join(map(str,tire_years))})"

    if 'tire_degradation' in st.session_state:
        degradation = st.session_state.tire_degradation
        sample_size = st.session_state.tire_sample_size
        label = st.session_state.tire_circuit_label

        st.markdown(f"<h3 style='border-left:4px solid #e10600;padding-left:12px'>{label}</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='color:#666'>Based on {sample_size} valid race laps</p>", unsafe_allow_html=True)

        # show the chart
        chart_data = degradation.rename(columns={'TyreLife': 'Tire Age (laps)', 'mean': 'Avg Lap Time (s)'})
        st.line_chart(chart_data.set_index('Tire Age (laps)')['Avg Lap Time (s)'])

        # calculate degradation rate
        if len(degradation) >= 5:
            first_avg = degradation.head(5)['mean'].mean()
            last_avg  = degradation.tail(5)['mean'].mean()
            span      = degradation['TyreLife'].max() - degradation['TyreLife'].min()
            deg_rate  = (last_avg - first_avg) / span if span > 0 else 0

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Fresh tire pace", f"{first_avg:.2f}s")
            with col2:
                st.metric("Worn tire pace", f"{last_avg:.2f}s")
            with col3:
                st.metric("Degradation rate", f"{deg_rate:.3f}s/lap")

            with st.expander("📋 Raw degradation data"):
                st.dataframe(degradation, use_container_width=True)

            # AI explanation
            st.divider()
            if st.button("🤖 Get AI Explanation"):
                with st.spinner("Analysing degradation pattern..."):
                    prompt = f"""Tire degradation data for {label}:

Fresh tire average lap time: {first_avg:.2f}s
Worn tire average lap time ({span} laps later): {last_avg:.2f}s
Degradation rate: {deg_rate:.3f} seconds per lap of tire age
Sample size: {sample_size} race laps from {', '.join(map(str,tire_years))}

Explain this degradation pattern:
1. Is this a high or low degradation rate compared to typical F1 tire behavior?
2. What does this mean practically for race strategy at this circuit?
3. At what tire age would a driver typically want to pit based on this curve?
4. What track characteristics likely cause this degradation level (high-speed corners, abrasive surface, traction zones, etc)?"""

                    messages = [
                        {"role": "system", "content": "You are an F1 tire engineer explaining degradation data to fans. Be specific and technical but clear."},
                        {"role": "user", "content": prompt}
                    ]
                    explanation = ask_groq(messages, max_tokens=600)
                    st.markdown(f"""
                    <div style='background:#1a0000;border:1px solid #e10600;border-radius:8px;padding:20px;margin-top:16px'>
                        <div style='color:#e10600;font-weight:700;margin-bottom:12px;font-size:0.85rem'>🔧 TIRE ENGINEER ANALYSIS</div>
                        <div style='color:#dddddd;line-height:1.7'>{explanation}</div>
                    </div>
                    """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style='text-align:center;padding:60px 20px'>
            <div style='font-size:3rem'>📊</div>
            <h3 style='color:white;border:none;padding:0'>Pick a circuit and compound to begin</h3>
            <p style='color:#888'>Real degradation curves built from years of actual race data.</p>
        </div>
        """, unsafe_allow_html=True)
