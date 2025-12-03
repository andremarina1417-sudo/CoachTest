import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import timedelta

# --- Configuration & User Zones ---
# We hardcode your specific zones here so the app knows YOU.
USER_FTP = 242
Z2_POWER_MIN = 140
Z2_POWER_MAX = 155
Z2_HR_CAP = 130
TARGET_CADENCE = 90

st.set_page_config(page_title="Runner's Cycle Coach", layout="wide")

st.title("🚴‍♂️ Runner's Cycle Coach")
st.markdown(f"""
**Current Profile:** FTP: **{USER_FTP}W** | Z2 Target: **{Z2_POWER_MIN}-{Z2_POWER_MAX}W** | HR Cap: **{Z2_HR_CAP} bpm**
""")

# --- Helper Functions ---

def parse_file(uploaded_file):
    """Parses CSV files (GOTOES export standard). FIT parsing requires binary lib, sticking to CSV for web app simplicity."""
    try:
        # Load with error skipping
        df_raw = pd.read_csv(uploaded_file, on_bad_lines='skip', low_memory=False)
        
        # Shift Detection Logic (The "GOTOES Bug" fix)
        is_shifted = False
        if 'GOTOES_CSV' in df_raw.columns:
            sample = df_raw['GOTOES_CSV'].dropna().iloc[0] if not df_raw['GOTOES_CSV'].dropna().empty else ""
            if isinstance(sample, str) and ('202' in sample or 'T' in sample):
                is_shifted = True
        
        df_clean = pd.DataFrame()
        
        if is_shifted:
            df_clean['timestamp'] = pd.to_datetime(df_raw['GOTOES_CSV'], errors='coerce')
            df_clean['heart_rate'] = pd.to_numeric(df_raw['altitude'], errors='coerce') 
            df_clean['cadence'] = pd.to_numeric(df_raw['heart_rate'], errors='coerce') 
            df_clean['power'] = pd.to_numeric(df_raw['speed'], errors='coerce')
        else:
            # Standard Mapping check
            col_map = {'timestamp': 'timestamp', 'heart_rate': 'heart_rate', 'cadence': 'cadence', 'power': 'power'}
            # If standard columns exist
            if 'power' in df_raw.columns:
                for k,v in col_map.items():
                    if v in df_raw.columns:
                        df_clean[k] = df_raw[v]
                if 'timestamp' in df_clean.columns:
                    df_clean['timestamp'] = pd.to_datetime(df_clean['timestamp'], errors='coerce')

        df_clean.dropna(subset=['timestamp', 'power'], inplace=True)
        return df_clean

    except Exception as e:
        st.error(f"Error parsing file: {e}")
        return pd.DataFrame()

def calculate_metrics(df):
    # Filter for active pedaling (exclude zeros) for accurate averages
    active = df[df['power'] > 10]
    
    if active.empty:
        return None

    duration_min = len(df) / 60
    avg_pwr = active['power'].mean()
    norm_pwr = np.sqrt(np.mean(active['power']**2)) # Simple RMS as proxy for NP
    avg_hr = active['heart_rate'].mean()
    avg_cad = active['cadence'].mean()
    
    # Efficiency Factor (EF)
    ef = avg_pwr / avg_hr if avg_hr > 0 else 0
    
    # Decoupling (Pw:HR)
    mid = len(active) // 2
    h1 = active.iloc[:mid]
    h2 = active.iloc[mid:]
    
    if len(h1) > 0 and len(h2) > 0:
        ef1 = h1['power'].mean() / h1['heart_rate'].mean()
        ef2 = h2['power'].mean() / h2['heart_rate'].mean()
        decoupling = (ef1 - ef2) / ef1 * 100
    else:
        decoupling = 0
        
    return {
        "duration": duration_min,
        "avg_pwr": avg_pwr,
        "norm_pwr": norm_pwr,
        "avg_hr": avg_hr,
        "avg_cad": avg_cad,
        "ef": ef,
        "decoupling": decoupling
    }

def generate_coach_feedback(metrics):
    feedback = []
    
    # 1. Power Check
    if metrics['avg_pwr'] < 115:
        feedback.append("🔵 **Recovery Ride:** Power was very low. Good for flushing legs, but minimal aerobic gain.")
    elif 125 <= metrics['avg_pwr'] <= 140:
        feedback.append("🟢 **Sweet Spot Z2:** Perfect execution for base building without leg fatigue.")
    elif 140 < metrics['avg_pwr'] <= 155:
        feedback.append("🟡 **High Z2:** Strong aerobic push. Ensure you fuel well after this.")
    elif metrics['avg_pwr'] > 160:
        feedback.append("🔴 **Intensity Alert:** This was a hard ride (Tempo/Threshold). Monitor leg freshness for running.")

    # 2. Decoupling Check
    if metrics['decoupling'] < 3:
        feedback.append("✅ **Efficiency:** Excellent! Less than 3% decoupling. Your engine is rock solid.")
    elif metrics['decoupling'] < 5:
        feedback.append("✅ **Efficiency:** Good. Standard drift.")
    else:
        feedback.append(f"⚠️ **Drift Alert:** Decoupling was {metrics['decoupling']:.1f}%. You faded in the second half. Check hydration/fueling.")

    # 3. Cadence Check
    if metrics['avg_cad'] < 85:
        feedback.append("🦶 **Grind Warning:** Avg Cadence {metrics['avg_cad']:.0f} is too low. This strains your running legs. Aim for 90+.")
    elif metrics['avg_cad'] > 90:
        feedback.append("💨 **Spin to Win:** Excellent cadence ({metrics['avg_cad']:.0f}). You saved your legs.")

    return feedback

# --- Main App Interface ---

uploaded_file = st.file_uploader("Upload your Ride (CSV from Intervals/GOTOES)", type=['csv'])

if uploaded_file is not None:
    df = parse_file(uploaded_file)
    
    if not df.empty:
        # Calculate
        m = calculate_metrics(df)
        
        # --- Top Level Stats ---
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Avg Power", f"{m['avg_pwr']:.0f} W")
        c2.metric("Avg HR", f"{m['avg_hr']:.0f} bpm")
        c3.metric("Decoupling", f"{m['decoupling']:.2f} %", delta_color="inverse")
        c4.metric("Efficiency (EF)", f"{m['ef']:.2f}")

        # --- Coach Feedback ---
        st.subheader("📢 Coach's Verdict")
        feedback = generate_coach_feedback(m)
        for item in feedback:
            st.markdown(item)

        # --- Deep Dive Charts ---
        st.subheader("📊 Ride Deep Dive")
        
        # 1. Power & HR Over Time
        # Downsample for speed if file is huge
        chart_df = df.iloc[::10, :].copy() 
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=chart_df['timestamp'], y=chart_df['power'], name='Power (W)', line=dict(color='purple', width=1)))
        fig.add_trace(go.Scatter(x=chart_df['timestamp'], y=chart_df['heart_rate'], name='HR (bpm)', line=dict(color='red', width=1), yaxis='y2'))
        
        fig.update_layout(
            title="Power vs Heart Rate",
            yaxis=dict(title="Watts"),
            yaxis2=dict(title="BPM", overlaying='y', side='right'),
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)

        # 2. Cadence Distribution
        fig_cad = px.histogram(df[df['cadence']>40], x="cadence", nbins=50, title="Cadence Distribution", color_discrete_sequence=['orange'])
        fig_cad.add_vline(x=TARGET_CADENCE, line_dash="dash", line_color="green", annotation_text="Target")
        st.plotly_chart(fig_cad, use_container_width=True)

    else:
        st.warning("Could not read data from file. Ensure it is a valid GOTOES or Intervals CSV.")
```

### **How to Deploy This (5 Minutes)**

1.  **Get the Code:** Copy the code block above and save it as a file named `app.py` on your computer.
2.  **GitHub:** Create a new repository on GitHub (call it "cycling-coach") and upload `app.py` there.
3.  **Requirements:** Add a file named `requirements.txt` in the same folder with these lines:
    ```
    streamlit
    pandas
    numpy
    plotly
