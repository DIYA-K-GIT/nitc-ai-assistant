import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import re

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.llms import Ollama
from langchain_community.retrievers import BM25Retriever
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document

CHROMA_DIR = "./chroma_db"
DB_PATH = "./college_rules.db"

# 1. Initialize API
app = FastAPI(title="NITC Notice Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    question: str

# 2. Advanced Vocabulary Synonym Map (Matching Friend's Features)
SYNONYM_MAP = {
    "fees": "tuition fee caution deposit fine semester registration financial payment",
    "fee": "tuition fee caution deposit fine semester registration financial payment",
    "backlog": "f grade failure repeat supplementary re-examination reexamination",
    "sick": "medical leave attendance condonation medical certificate",
    "final semester": "eighth semester 8th semester graduation project",
    "placement": "internship project drive campus recruitment credits"
}

# 3. Load the RAG Engine Globally
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
vector_store = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)
chroma_retriever = vector_store.as_retriever(search_kwargs={"k": 3})

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT rule_text, rule_number, filename FROM rules JOIN documents ON rules.doc_id = documents.id")
rows = cursor.fetchall()
conn.close()

bm25_docs = [Document(page_content=r[0], metadata={"rule": r[1], "source": r[2]}) for r in rows]
bm25_retriever = BM25Retriever.from_documents(bm25_docs)
bm25_retriever.k = 3

llm = Ollama(model="llama3.2:3b", temperature=0.1, base_url="http://127.0.0.1:11434")

def log_to_db(user_query, rewritten_query, response):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_logs (user_query, rewritten_query, bot_response) VALUES (?, ?, ?)", 
                       (user_query, rewritten_query, response))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Logging error: {e}")

# 4. Create the Chat Endpoint
@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        user_query = request.question.lower().strip()
        
        # FEATURE 1 FIXED: Now accurately detects multi-word phrases like "final semester"
        expanded_keywords = ""
        for key, value in SYNONYM_MAP.items():
            if key in user_query:
                expanded_keywords += f" {value}"
        
        search_query = f"{user_query} {expanded_keywords}".strip()
        
        # Let the LLM rewrite the enhanced query into targeted search keywords
        rewrite_prompt = PromptTemplate.from_template("Rewrite this question into 3-5 formal academic keywords. Output ONLY the keywords. Question: {question}\nKeywords:")
        rewritten_query = llm.invoke(rewrite_prompt.format(question=search_query)).strip()
        
        # FEATURE 3: The Rewrite Failsafe (Matching your friend's logic)
        # If the LLM gets chatty or outputs too many words, throw it away and use the original query
        if len(rewritten_query.split()) > 10 or "Here" in rewritten_query or "keywords" in rewritten_query.lower():
            print(f"\n[WARNING] LLM generated a bad rewrite: {rewritten_query}")
            rewritten_query = search_query
            
        print(f"\n[DEBUG] Searching Database With: '{rewritten_query}'\n")
        
        # Retrieve context from both engines
        bm25_docs = bm25_retriever.invoke(rewritten_query)
        vector_docs = chroma_retriever.invoke(rewritten_query)
        
        unique_docs = {d.page_content: d for d in bm25_docs + vector_docs}
        retrieved_docs = list(unique_docs.values())[:4]
        
        # --- DEBUG VISUALIZER ---
        print("--- WHAT THE DATABASE FOUND ---")
        for i, doc in enumerate(retrieved_docs):
            print(f"Doc {i+1} [Rule: {doc.metadata.get('rule')}]: {doc.page_content[:150]}...")
        print("-------------------------------\n")

        # Handle case where absolutely no data is found to prevent LLM crashes
        if not retrieved_docs:
            return {"answer": "I cannot find any specific information regarding that topic in the current institutional regulations."}
            
        context = "\n\n".join([f"[Source: {d.metadata.get('source')} | Rule: {d.metadata.get('rule')}]:\n{d.page_content}" for d in retrieved_docs])
        
        qa_prompt = PromptTemplate.from_template("""You are an official administrative AI chat assistant for NIT Calicut. 
        Answer based STRICTLY on the context below. Cite the specific Rule Number or Source Document.
        If the answer is not in the context, respond strictly with: "I cannot find that information in the recently posted notifications." Do not guess.
        
        Context:
        {context}
        
        Question: {question}
        Helpful Administrative Answer:""")
        
        raw_response = llm.invoke(qa_prompt.format(context=context, question=user_query))
        
        # FEATURE 2: Defensive Response Parsing (Guarantees frontend never gets undefined)
        final_response = str(raw_response).strip() if raw_response else "I am having trouble parsing the regulations for this query. Please try phrasing it more formally."
        
        log_to_db(user_query, rewritten_query, final_response)
        return {"answer": final_response}
        
    except Exception as e:
        import traceback
        print("\n" + "="*50)
        print("CRITICAL ENGINE ERROR:")
        traceback.print_exc()
        print("="*50 + "\n")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)