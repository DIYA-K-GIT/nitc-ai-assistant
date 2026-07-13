import os
import re
import sqlite3
import fitz  # PyMuPDF (Faster and better for text extraction than pypdf)
from pdf2image import convert_from_path
import pytesseract

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

# Define paths matching your structure
RAW_DIR = "./raw_notices"
TEXT_DIR = "./extracted_text"
CHROMA_DIR = "./chroma_db"
DB_PATH = "./college_rules.db"

os.makedirs(TEXT_DIR, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)

# --- 1. SQLite Database Setup ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT UNIQUE, status TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS rules (id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id INTEGER, rule_number TEXT, rule_text TEXT, FOREIGN KEY(doc_id) REFERENCES documents(id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS chat_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_query TEXT, rewritten_query TEXT, bot_response TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    return conn

# --- 2. Smart Hybrid Extraction (Native + OCR) ---
def extract_text_hybrid(pdf_path):
    print(f"\nParsing: {os.path.basename(pdf_path)}...")
    doc = fitz.open(pdf_path)
    full_text = ""
    
    # We go page by page. If a page has native text, we grab it. If it's a scanned image, we OCR it.
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        page_text = page.get_text("text").strip()
        
        # OCR Fallback trigger: If the page is essentially empty of selectable text
        if len(page_text) < 50:
            print(f" -> Page {page_num + 1} looks scanned. Running OCR via pytesseract...")
            try:
                images = convert_from_path(pdf_path, first_page=page_num+1, last_page=page_num+1)
                page_text = pytesseract.image_to_string(images[0])
            except Exception as e:
                print(f" -> OCR breakdown on page {page_num + 1}: {e}")
                page_text = ""
                
        full_text += page_text + "\n\n"
    return full_text

# --- 3. Dynamic NITC Chunker ---
def chunk_documents(text, filename):
    # Matches patterns like "R.1", "R.1.1", "R.2.1.a", etc., at the start of a line
    rule_pattern = re.compile(r'(?m)^(R\.\d+(?:\.\d+)*[a-z]?\s+.*)')
    parts = rule_pattern.split(text)
    
    chunks = []
    
    # If the document actually contains structured rules (more than 2 matches)
    if len(parts) > 2:
        print(" -> Detected structured rules (R.x). Applying custom NITC chunking...")
        current_rule = "General Context"
        
        for part in parts:
            part = part.strip()
            if not part: continue
            
            if rule_pattern.match(part):
                current_rule = part.split(' ', 1)[0] # Extract just the "R.1.x" part
                chunks.append(Document(page_content=part, metadata={"source": filename, "rule": current_rule}))
            else:
                if chunks:
                    chunks[-1].page_content += "\n" + part
                else:
                    chunks.append(Document(page_content=part, metadata={"source": filename, "rule": "Intro"}))
        return chunks
    
    # Fallback: If it's a normal notice without 'R.x' rules, use your original Recursive chunker!
    print(" -> No structured rules found. Falling back to Recursive Character splitting...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=100)
    base_doc = Document(page_content=text, metadata={"source": filename, "rule": "General Info"})
    return text_splitter.split_documents([base_doc])

# --- 4. Main Ingestion Loop ---
def build_vector_db():
    pdf_files = [f for f in os.listdir(RAW_DIR) if f.endswith('.pdf')]
    if not pdf_files:
        print(f"Empty directory! Drop your scanned NITC PDFs into the '{RAW_DIR}' folder first.")
        return

    conn = init_db()
    cursor = conn.cursor()
    
    print("Loading local Hugging Face embedding model...")
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vector_store = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)

    total_chunks = 0
    
    for file in pdf_files:
        # Check SQLite to avoid re-processing the same PDF
        cursor.execute("SELECT id FROM documents WHERE filename = ?", (file,))
        if cursor.fetchone():
            print(f"\nSkipping {file} (Already processed and logged in SQLite Database)")
            continue

        pdf_path = os.path.join(RAW_DIR, file)
        
        # 1. Extract
        text_content = extract_text_hybrid(pdf_path)
        
        # 2. Save your raw text copy
        txt_filename = file.replace(".pdf", ".txt")
        with open(os.path.join(TEXT_DIR, txt_filename), "w", encoding="utf-8") as f:
            f.write(text_content)
            
        # 3. Chunk
        chunks = chunk_documents(text_content, file)
        total_chunks += len(chunks)
        
        # 4. Save to SQLite Relational DB
        cursor.execute("INSERT INTO documents (filename, status) VALUES (?, ?)", (file, "processed"))
        doc_id = cursor.lastrowid
        
        for chunk in chunks:
            cursor.execute("INSERT INTO rules (doc_id, rule_number, rule_text) VALUES (?, ?, ?)", 
                           (doc_id, chunk.metadata.get("rule", "General Info"), chunk.page_content))
        conn.commit()
        
        # 5. Save to Vector DB
        vector_store.add_documents(chunks)
        print(f" -> Ingested {len(chunks)} chunks into the system.")

    conn.close()
    if total_chunks > 0:
        print(f"\nDone! Your databases are populated with {total_chunks} new searchable chunks.")
    else:
        print("\nDatabase is already up to date!")

if __name__ == "__main__":
    build_vector_db()