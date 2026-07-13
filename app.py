import sqlite3
import streamlit as st
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.llms import Ollama
from langchain_community.retrievers import BM25Retriever

from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document

CHROMA_DIR = "./chroma_db"
DB_PATH = "./college_rules.db"

st.set_page_config(page_title="NITC Portal Sandbox", page_icon="🏫", layout="wide")

# --- TRICK: CSS INJECTION FOR FLOATING POPUP CHATBOT ---
st.markdown("""
    <style>
    .block-container { padding-top: 2rem; }
    .mock-site {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #dee2e6;
        margin-bottom: 20px;
    }
    /* Fixed Floating Chat Container in Bottom Right Corner */
    div[data-testid="stColumn"]:nth-child(2) {
        position: fixed;
        bottom: 20px;
        right: 20px;
        background-color: white;
        z-index: 99999;
        padding: 15px;
        border-radius: 15px;
        box-shadow: 0px 10px 30px rgba(0,0,0,0.15);
        border: 1px solid #e0e0e0;
        max-height: 70vh;
        overflow-y: auto;
    }
    </style>
""", unsafe_allow_html=True)

# --- BACKGROUND: SIMULATED NITC WEBSITE CONTENT ---
st.markdown("""
<div class="mock-site">
    <h2>National Institute of Technology Calicut (NITC)</h2>
    <p style="color: gray;">Official Institutional Portal Sandbox (Hybrid AI Active)</p>
    <hr>
    <h5>Latest Updates & Quick Links</h5>
    <ul>
        <li>Academic Calendar 2026-2027</li>
        <li>B.Tech/M.Tech Monsoon Semester Registration Link</li>
        <li>PG/Ph.D Admission Notifications</li>
    </ul>
    <p style="font-size: 13px; color: #888;">This layout simulates the actual NITC website structure for your internship project demo.</p>
</div>
""", unsafe_allow_html=True)

# --- UTILITY: SQLITE CHAT LOGGING ---
def log_to_db(user_query, rewritten_query, response):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_logs (user_query, rewritten_query, bot_response) VALUES (?, ?, ?)", 
                       (user_query, rewritten_query, response))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database logging error: {e}")

# --- BACKEND: LOAD ADVANCED HYBRID RAG SYSTEM ---
@st.cache_resource
def load_rag_system():
    # 1. Semantic Vector Store (Chroma)
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vector_store = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)
    chroma_retriever = vector_store.as_retriever(search_kwargs={"k": 3})
    
    # 2. Exact Keyword Store (BM25 via SQLite)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT rule_text, rule_number, filename FROM rules JOIN documents ON rules.doc_id = documents.id")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        raise ValueError("Database is empty. Please run pipeline.py first to ingest PDFs.")
        
    bm25_docs = [Document(page_content=r[0], metadata={"rule": r[1], "source": r[2]}) for r in rows]
    bm25_retriever = BM25Retriever.from_documents(bm25_docs)
    bm25_retriever.k = 3 # Fetch top 3 exact keyword matches
    
    # REMOVED ENSEMBLE RETRIEVER - Returning them separately
    llm = Ollama(model="llama3", temperature=0.1, base_url="http://127.0.0.1:11434")
    
    return bm25_retriever, chroma_retriever, llm

# --- CHAT UI LAYOUT ---
col1, col2 = st.columns([2.5, 1])

with col2:
    st.subheader("💬 NITC Notice Bot")
    
    try:
        # FIXED: Now properly unpacking all 3 variables returned by load_rag_system()
        bm25_retriever, chroma_retriever, llm = load_rag_system()
    except Exception as e:
        st.error(f"RAG Engine Error: {str(e)}")
        st.stop()

    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Hello! Ask me any questions regarding recently published NITC PDF notices. I will cite the exact rule number."}]

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_query := st.chat_input("Ask about a notice or rule..."):
        st.session_state.messages.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing and cross-referencing rules..."):
                try:
                    # STEP A: Query Rewriting
                    rewrite_prompt = PromptTemplate.from_template("Rewrite this question into 3-5 formal keywords to search an academic rulebook. Output ONLY the keywords. Question: {question}\nKeywords:")
                    rewritten_query = llm.invoke(rewrite_prompt.format(question=user_query)).strip()
                    
                    # STEP B: Manual Hybrid Retrieval
                    # 1. Fetch exact keywords
                    bm25_docs = bm25_retriever.invoke(rewritten_query)
                    # 2. Fetch semantic matches
                    vector_docs = chroma_retriever.invoke(rewritten_query)
                    
                    # 3. Combine and remove duplicates
                    unique_docs = {d.page_content: d for d in bm25_docs + vector_docs}
                    retrieved_docs = list(unique_docs.values())[:4] # Keep top 4 results
                    
                    # Assemble the context
                    context = "\n\n".join([f"[Source: {d.metadata.get('source')} | Rule: {d.metadata.get('rule', 'General')}]:\n{d.page_content}" for d in retrieved_docs])
                    
                    # STEP C: Generate strict response
                    qa_prompt = PromptTemplate.from_template("""You are an official administrative AI chat assistant for NIT Calicut. 
                    Answer the question based STRICTLY on the context below. 
                    You MUST cite the specific Rule Number or Source Document provided in the context when answering.
                    If the answer is not in the context, respond strictly with: "I cannot find that information in the recently posted notifications." Do not guess.
                    
                    Context:
                    {context}
                    
                    Question: {question}
                    Helpful Administrative Answer:""")
                    
                    final_response = llm.invoke(qa_prompt.format(context=context, question=user_query))
                    
                    # Output response to UI and log silently to DB
                    st.markdown(final_response)
                    st.session_state.messages.append({"role": "assistant", "content": final_response})
                    log_to_db(user_query, rewritten_query, final_response)
                    
                except Exception as e:
                    st.error(f"Engine Error: {str(e)}")