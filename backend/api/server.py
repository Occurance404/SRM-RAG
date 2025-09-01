import argparse
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sys
import os
from pathlib import Path
import google.generativeai as genai
from fastapi.middleware.cors import CORSMiddleware

# Add the project root to the Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from retrieval.search import search as perform_search

# --- Gemini API Configuration ---
try:
    GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
except KeyError:
    print("FATAL: GEMINI_API_KEY environment variable not set.")
    sys.exit(1)

# Initialize FastAPI app
app = FastAPI(
    title="University RAG API",
    description="An API for searching a university website and generating answers with an LLM.",
    version="2.0.0",
)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models ---
class QueryRequest(BaseModel):
    query: str
    n_results: int = 3

class SearchResult(BaseModel):
    score: float
    url: str
    text: str

class QueryResponse(BaseModel):
    answer: str
    sources: list[SearchResult]

# --- LLM Prompting ---
def generate_llm_answer(query: str, context: str) -> str:
    """Generates an answer using the Gemini model."""
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""
You are a helpful assistant for the SRM University, Andhra Pradesh.
Answer the following question based *only* on the context provided below.
If the context does not contain the answer, say "I'm sorry, but I cannot answer this question based on the provided information."

Question: {query}

Context:
---
{context}
---
"""
    try:
        response = model.generate_content(prompt)
        return getattr(response, "text", str(response))
    except Exception as e:
        print(f"Error during LLM generation: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate an answer from the language model.")

# --- API Endpoints ---
@app.get("/healthz", summary="Health Check")
def health_check():
    return {"status": "ok"}

@app.post("/query", response_model=QueryResponse, summary="Perform a RAG search and generate an answer")
def query_endpoint(request: QueryRequest):
    try:
        search_results = perform_search(
            db_path="D:\\Semester2\\srm_project\\data\\chroma_db",
            collection_name="university_rag",
            query=request.query,
            n_results=max(1, request.n_results),
            verbose=False
        )
    except Exception as e:
        print(f"Error during search: {e}")
        raise HTTPException(status_code=500, detail="Error while searching the vector database.")

    if not search_results:
        return QueryResponse(answer="Could not find any relevant documents to answer the question.", sources=[])

    sources = [
        SearchResult(
            score=res['score'],
            url=res['metadata'].get('url', ''),
            text=res['document']
        )
        for res in search_results
    ]

    context_parts = [f"Source URL: {s.url}\\nContent: {s.text}" for s in sources]
    context = "\\n\\n---\\n\\n".join(context_parts)

    answer = generate_llm_answer(request.query, context)

    return QueryResponse(answer=answer, sources=sources)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the FastAPI server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to run the server on.")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on.")
    args = parser.parse_args()

    print(f"Starting server at http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)