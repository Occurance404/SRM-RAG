import chromadb
import argparse
import json
from sentence_transformers import SentenceTransformer, CrossEncoder

def search(db_path: str, collection_name: str, query: str, n_results: int, verbose: bool = True):
    """
    Searches a ChromaDB collection for a given query, then reranks the results.
    Returns a list of result dictionaries.
    """
    if verbose:
        print("Initializing models...")
    bi_encoder = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')
    cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

    # --- 1. Initial Search (Candidate Generation) ---
    if verbose:
        print(f"Connecting to ChromaDB at: {db_path}")
    client = chromadb.PersistentClient(path=db_path)
    collection = client.get_or_create_collection(name=collection_name)
    if verbose:
        print(f"Successfully connected to collection '{collection_name}'.")

    if verbose:
        print(f"\nStep 1: Performing initial search for: '{query}'...")
    query_embedding = bi_encoder.encode(query).tolist()
    
    candidate_results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(25, collection.count())
    )

    initial_docs = candidate_results.get('documents', [[]])[0]
    initial_metadatas = candidate_results.get('metadatas', [[]])[0]
    if verbose:
        print(f"Found {len(initial_docs)} initial candidates.")

    # --- 2. Reranking with Cross-Encoder ---
    if not initial_docs:
        if verbose:
            print("No initial results found. Exiting.")
        return []

    if verbose:
        print("\nStep 2: Reranking with Cross-Encoder...")
    sentence_pairs = [[query, doc] for doc in initial_docs]
    
    scores = cross_encoder.predict(sentence_pairs, show_progress_bar=verbose)

    reranked_results = []
    for i in range(len(initial_docs)):
        reranked_results.append({
            'score': scores[i],
            'document': initial_docs[i],
            'metadata': initial_metadatas[i]
        })

    reranked_results.sort(key=lambda x: x['score'], reverse=True)

    # --- 3. Return Top Results ---
    return reranked_results[:n_results]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Search the ChromaDB vector index with reranking.")
    parser.add_argument("-q", "--query", required=True, help="The search query.")
    parser.add_argument("--db-path", default="data/chroma_db", help="Path to the ChromaDB database.")
    parser.add_argument("--collection-name", default="university_rag", help="Name of the ChromaDB collection.")
    parser.add_argument("--n-results", type=int, default=3, help="Number of final results to return.")
    args = parser.parse_args()

    # When run as a script, call search and print the results
    final_results = search(args.db_path, args.collection_name, args.query, args.n_results)
    
    if final_results:
        print(f"\n--- Top {len(final_results)} Reranked Results ---")
        for i, result in enumerate(final_results):
            print(f"\n--- Result {i+1} (Score: {result['score']:.4f}) ---")
            print(f"URL: {result['metadata'].get('url')}")
            print(f"Text: {result['document']}")
            print("-" * 20)
