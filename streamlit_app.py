import asyncio
import os
import time
from pathlib import Path

import inngest
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
st.set_page_config(page_title="RAG Ingest PDF", layout="centered")

INNGEST_API_BASE = os.getenv("INNGEST_API_BASE", "http://127.0.0.1:8288/v1")


@st.cache_resource
def client() -> inngest.Inngest:
    return inngest.Inngest(app_id="rag_app", is_production=False)


def save_pdf(file) -> Path:
    path = Path("uploads") / file.name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(file.getbuffer())
    return path


async def send_event(name: str, data: dict):
    result = await client().send(inngest.Event(name=name, data=data))
    return result[0]


def wait_for_output(event_id: str, timeout_s: float = 120.0, poll_s: float = 0.5) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        runs = requests.get(f"{INNGEST_API_BASE}/events/{event_id}/runs").json().get("data", [])
        if runs:
            status = runs[0].get("status")
            if status in ("Completed", "Succeeded", "Success", "Finished"):
                return runs[0].get("output") or {}
            if status in ("Failed", "Cancelled"):
                raise RuntimeError(f"Run {status}")
        time.sleep(poll_s)
    raise TimeoutError("Timed out waiting for run output")


# --- Ingest ---
st.title("RAG PDF Assistant")
st.subheader("Upload a PDF")

uploaded = st.file_uploader("Choose a PDF", type=["pdf"])
if uploaded:
    with st.spinner("Uploading..."):
        path = save_pdf(uploaded)
        asyncio.run(send_event("rag/ingest_pdf", {
            "pdf_path": str(path.resolve()),
            "source_id": path.name,
        }))
    st.success(f"Ingesting: {path.name}")

st.divider()

# --- Query ---
st.subheader("Ask a question")

with st.form("query_form"):
    question = st.text_input("Your question")
    top_k = st.number_input("Chunks to retrieve", 1, 20, 5)
    submitted = st.form_submit_button("Ask")

if submitted and question.strip():
    with st.spinner("Thinking..."):
        event_id = asyncio.run(send_event("rag/query_pdf_ai", {
            "question": question.strip(),
            "top_k": int(top_k),
        }))
        output = wait_for_output(event_id)

    st.write(output.get("answer") or "(No answer)")
    if sources := output.get("sources"):
        with st.expander("Sources"):
            for s in sources:
                st.write(f"- {s}")