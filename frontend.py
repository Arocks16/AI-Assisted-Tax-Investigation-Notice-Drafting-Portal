# Streamlit frontend for Phase 1 (Investigation) + Phase 2 (Notice Drafting)
# Flow: select case → Phase 1 → AO review → Phase 2 (draft → review → refine loop → done)

import streamlit as st
from backend import graph
from langgraph.types import Command
from fpdf import FPDF

st.set_page_config(page_title="Tax Investigation Portal", layout="wide")
st.markdown("""
<style>
.report-container { max-width: 900px; margin: 0 auto; }
.report-container table { font-size: 0.85em; word-break: break-word; }
</style>
""", unsafe_allow_html=True)
st.title("Tax Investigation & Notice Drafting Portal")

# ── Session state ────────────────────────────────────────

if "step" not in st.session_state:
    st.session_state.clear()
    st.session_state.step = "select"

# ── PDF helper ───────────────────────────────────────────

def generate_pdf(text: str, din: str = "") -> bytes:
    # Strip markdown formatting
    for ch in ("*", "#"):
        text = text.replace(ch, "")
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(18, 12, 18)
    pdf.add_page()
    lm = pdf.l_margin
    rw = pdf.w - lm - pdf.r_margin  # usable width
    # Header
    pdf.set_x(lm)
    pdf.set_font("Courier", "B", 12)
    pdf.cell(rw, 7, "INCOME TAX DEPARTMENT", ln=True)
    pdf.set_x(lm)
    pdf.set_font("Courier", "B", 10)
    pdf.cell(rw, 6, "Scrutiny Notice u/s 142(1)", ln=True)
    if din:
        pdf.set_x(lm)
        pdf.set_font("Courier", "", 8)
        pdf.cell(rw, 5, "DIN: " + din, ln=True)
    pdf.ln(5)
    # Body
    pdf.set_font("Courier", "", 9)
    for line in text.split("\n"):
        raw = line.strip()
        if not raw:
            pdf.ln(2.5)
            continue
        s = raw.encode("ascii", "replace").decode("ascii")
        pdf.set_x(lm)
        if s.startswith("Subject:"):
            pdf.set_font("Courier", "B", 9)
            pdf.multi_cell(rw, 4.2, s)
            pdf.set_font("Courier", "", 9)
        else:
            pdf.multi_cell(rw, 4.2, s)
    # Footer
    pdf.ln(5)
    pdf.set_x(lm)
    pdf.set_font("Courier", "I", 7)
    pdf.multi_cell(rw, 3.5, "This is a computer-generated notice. No signature required.")
    return bytes(pdf.output())

# ── Step 1: Case selection ───────────────────────────────

if st.session_state.step == "select":
    case = st.selectbox("Select Case", [
        "CASE-2025-001 — Rahul Sharma"
    ])
    if st.button("Start Investigation"):
        st.session_state.config = {"configurable": {"thread_id": case.split(" — ")[0]}}
        st.session_state.step = "running"
        st.rerun()

# ── Step 2: Phase 1 — Run investigation ─────────────────

if st.session_state.step == "running":
    with st.spinner("Running investigation... this may take a moment."):
        try:
            initial = {"itr_text": "", "form16_text": "", "ais_text": "", "investigation": "", "report": "", "ao_decision": "", "draft_notice_text": "", "ao_feedback": "", "din": ""}
            for _ in graph.stream(initial, st.session_state.config, stream_mode="updates"):
                pass
            state = graph.get_state(st.session_state.config)
            st.session_state.report = state.values.get("report", "")
            st.session_state.step = "review"
            st.rerun()
        except Exception as e:
            st.error(f"Investigation failed: {e}")
            if st.button("Try Again"):
                st.session_state.clear()
                st.rerun()

# ── Step 3: Phase 1 — AO review ─────────────────────────

if st.session_state.step == "review":
    st.markdown("### Investigation Report")
    with st.container():
        st.markdown(f'<div class="report-container">{st.session_state.report or "_No report generated."}</div>', unsafe_allow_html=True)
    st.divider()
    decision = st.radio("Initiate Draft Notice?", ["Yes", "No"], horizontal=True)
    if st.button("Submit Decision"):
        try:
            for _ in graph.stream(Command(resume={"answer": decision.lower()}), st.session_state.config, stream_mode="updates"):
                pass
            state = graph.get_state(st.session_state.config)
            # Check if Phase 2 started (interrupt has "draft_notice" key)
            if state.interrupts and "draft_notice" in state.interrupts[0].value:
                st.session_state.draft_notice_text = state.interrupts[0].value["draft_notice"]
                st.session_state.step = "phase2_review"
            else:
                st.session_state.result = decision
                st.session_state.step = "result"
            st.rerun()
        except Exception as e:
            st.error(f"Failed to submit decision: {e}")

# ── Step 4: Phase 2 — Review / refine draft notice ──────

if st.session_state.step == "phase2_review":
    st.markdown("### Draft Scrutiny Notice — Section 142(1)")
    with st.container():
        st.markdown(f'<div class="report-container">{st.session_state.draft_notice_text}</div>', unsafe_allow_html=True)
    st.divider()
    feedback = st.text_area("Feedback (leave blank to approve, or write changes):")
    col1, col2 = st.columns(2)
    with col1:
        approve = st.button("Approve", use_container_width=True)
    with col2:
        revise = st.button("Send Feedback", use_container_width=True)
    if approve or revise:
        fb = "" if approve else feedback
        try:
            for _ in graph.stream(Command(resume={"feedback": fb}), st.session_state.config, stream_mode="updates"):
                pass
            state = graph.get_state(st.session_state.config)
            if state.interrupts and "draft_notice" in state.interrupts[0].value:
                st.session_state.draft_notice_text = state.interrupts[0].value["draft_notice"]
                st.session_state.step = "phase2_review"
            else:
                st.session_state.din = state.values.get("din", "")
                st.session_state.final_notice = state.values.get("draft_notice_text", "")
                st.session_state.step = "phase2_done"
            st.rerun()
        except Exception as e:
            st.error(f"Failed: {e}")

# ── Step 5: Phase 2 — Final result with PDF download ────

if st.session_state.step == "phase2_done":
    st.success("Case Complete — Scrutiny Notice Finalised")
    if st.session_state.final_notice:
        pdf_bytes = generate_pdf(st.session_state.final_notice, st.session_state.din)
        st.download_button("Download PDF", data=pdf_bytes, file_name="notice.pdf", mime="application/pdf")
    if st.button("Start New Investigation"):
        st.session_state.clear()
        st.rerun()

# ── Step 6: Phase 1 — No, case closed ───────────────────

if st.session_state.step == "result":
    if st.session_state.result == "Yes":
        st.success("Draft Notice Initiated")
    else:
        st.info("Case Closed")
    if st.button("Start New Investigation"):
        st.session_state.clear()
        st.rerun()