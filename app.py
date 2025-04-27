import streamlit as st
import pandas as pd
import googlemaps
import folium
from folium import PolyLine, Marker
from streamlit_folium import st_folium
from datetime import timedelta
from llama_index.llms.groq import Groq
from llama_index.core.prompts import PromptTemplate

st.set_page_config(page_title="🗺️ AI Route Optimizer", layout="wide")

gmaps = googlemaps.Client(key=st.secrets["GOOGLE_MAPS_API_KEY"])
llm = Groq(model="llama3-8b-8192", api_key=st.secrets["GROQ_API_KEY"])

def format_duration(sec: int) -> str:
    td = timedelta(seconds=sec)
    h, rem = divmod(td.seconds, 3600)
    m = rem // 60
    return f"{h}h {m}m"

def fetch_directions(start, end, stops, optimize=False):
    return gmaps.directions(
        origin=start,
        destination=end,
        waypoints=stops,
        optimize_waypoints=optimize
    )[0]

def route_list(dirs, stops, optimized=False):
    ordered = [stops[i] for i in dirs["waypoint_order"]] if optimized else stops.copy()
    legs = dirs["legs"]
    return [legs[0]["start_address"]] + ordered + [legs[-1]["end_address"]]

def metrics(dirs):
    dist = sum(l["distance"]["value"] for l in dirs["legs"]) / 1000
    dur = sum(l["duration"]["value"] for l in dirs["legs"])
    return dist, dur

def coords_from(dirs):
    pts = [(leg["start_location"]["lat"], leg["start_location"]["lng"]) for leg in dirs["legs"]]
    pts.append((dirs["legs"][-1]["end_location"]["lat"], dirs["legs"][-1]["end_location"]["lng"]))
    return pts

st.title("🗺️ AI-Powered Last Mile Delivery")

with st.sidebar.form("inputs"):
    st.header("🚩 Route Inputs")
    start = st.text_input("Starting Address")
    end = st.text_input("Destination Address")
    upload = st.file_uploader("Excel of Stops (.xlsx)")
    submit = st.form_submit_button("Optimize Route 🚀")

stops = []
if upload:
    df = pd.read_excel(upload)
    stops = df.iloc[:, 0].dropna().astype(str).tolist()

if submit:
    if not (start and end and stops):
        st.sidebar.error("Fill start, end & upload stops file.")
    else:
        try:
            raw1 = fetch_directions(start, end, stops, optimize=False)
            raw2 = fetch_directions(start, end, stops, optimize=True)
        except Exception as e:
            st.error(f"Directions API error: {e}")
            st.stop()

        st.session_state.raw1 = raw1
        st.session_state.raw2 = raw2
        st.session_state.r1 = route_list(raw1, stops, False)
        st.session_state.r2 = route_list(raw2, stops, True)

if "r2" in st.session_state:
    d1, t1 = metrics(st.session_state.raw1)
    d2, t2 = metrics(st.session_state.raw2)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("▶️ Before Distance", f"{d1:.1f} km")
    c2.metric("▶️ Before Duration", format_duration(t1))
    c3.metric("✨ After Distance", f"{d2:.1f} km")
    c4.metric("✨ After Duration", format_duration(t2))

    st.subheader("📍 Input Route")
    st.table(pd.DataFrame({"Order": range(1,len(st.session_state.r1)+1), "Address": st.session_state.r1}))
    st.subheader("✨ Optimized Route")
    st.table(pd.DataFrame({"Order": range(1,len(st.session_state.r2)+1), "Address": st.session_state.r2}))

    # --- Create folium map with height ---
    m = folium.Map(
        location=coords_from(st.session_state.raw1)[0],
        zoom_start=12,
        control_scale=True,
        height=700  # Very important!
    )

    PolyLine(coords_from(st.session_state.raw1), dash_array="5,5", weight=3,
             color="blue", tooltip="Before").add_to(m)

    PolyLine(coords_from(st.session_state.raw2), weight=3,
             color="red", tooltip="Optimized").add_to(m)

    for i, pt in enumerate(coords_from(st.session_state.raw2)):
        Marker(pt, popup=f"{i + 1}. {st.session_state.r2[i]}").add_to(m)

    # --- Render nicely in Streamlit ---
    st.subheader("🗺️ Map View")
    st_folium(m, height=700, width=None, use_container_width=True)

    # Shrink white gap manually
    st.markdown("<div style='margin-top: -50px;'></div>", unsafe_allow_html=True)
    st.divider()

    st.subheader("💡 Suggested Questions")
    questions = [
        "What is the total distance of the optimized route?",
        "How long will it take to complete this route?",
        "Are there notable landmarks or attractions along this route?",
        "Are there traffic hotspots along this route?",
        "Can I customize this route by adding or removing stops?"
    ]

    cols = st.columns(2)
    for idx, q in enumerate(questions):
        if cols[idx % 2].button(q, key=f"q{idx}"):
            qa_template = PromptTemplate("Route:\n{route}\n\nQ: {question}\nA:")
            ans = llm.predict(qa_template, route="\n".join(st.session_state.r2), question=q)
            with st.expander(f"✅ {q}"):
                st.info(ans)

    st.subheader("❓ Ask a Custom Route Question")
    uq = st.text_input("Type your question here:", key="uq")
    if st.button("Get Answer 🚀", key="send_uq"):
        qa_template = PromptTemplate("Route:\n{route}\n\nQ: {question}\nA:")
        ans = llm.predict(qa_template, route="\n".join(st.session_state.r2), question=uq)
        st.success(ans)

    st.subheader("💬 Groq Chat Playground")
    chat_input = st.text_area("Chat with LLM:", key="chat")
    if st.button("Chat 💬", key="chat_go"):
        general_template = PromptTemplate("{query}")
        response = llm.predict(general_template, query=chat_input)
        st.write(response)

else:
    st.info("📝 Fill in the sidebar & click **Optimize Route 🚀** to begin.")
