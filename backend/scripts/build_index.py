import json
import chromadb
from sentence_transformers import SentenceTransformer
from pathlib import Path
from tqdm import tqdm

def build_index(input_file: Path, db_path: str, collection_name: str):
    """
    Builds a ChromaDB index from a JSONL file of enriched chunks.
    """
    # 1. Initialize embedding model
    print("Initializing sentence-transformer model...")
    model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu') 

    # 2. Initialize ChromaDB client
    print(f"Initializing ChromaDB client at: {db_path}")
    client = chromadb.PersistentClient(path=db_path)
    
    # 3. Create or get the collection
    print(f"Deleting existing collections to ensure a clean slate.")
    try:
        client.delete_collection(name="university_rag")
        print("Deleted old 'university_rag' collection.")
    except Exception as e:
        print("Old 'university_rag' collection not found, skipping.")
    try:
        client.delete_collection(name="university_rag_v2")
        print("Deleted old 'university_rag_v2' collection.")
    except Exception as e:
        print("Old 'university_rag_v2' collection not found, skipping.")

    print(f"Getting or creating collection: {collection_name}")
    collection = client.get_or_create_collection(name=collection_name)

    # 4. Read the enriched data and process in batches
    print(f"Processing file: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    batch_size = 128
    for i in tqdm(range(0, len(lines), batch_size), desc="Indexing batches"):
        batch_lines = lines[i:i+batch_size]
        batch_data = [json.loads(line) for line in batch_lines]

        ids = [chunk['chunk_id'] for chunk in batch_data]
        documents = [chunk['text'] for chunk in batch_data]
        metadatas = [
            {
                "url": chunk.get('url', ''),
                "title": chunk.get('title', ''),
                "entities": json.dumps(chunk.get('entities', {})),
                "images": json.dumps(chunk.get('images', []))
            }
            for chunk in batch_data
        ]

        embeddings = model.encode(documents, show_progress_bar=False).tolist()

        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )

    print("\nIndexing complete.")

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Build a ChromaDB vector index from enriched text chunks.")
    parser.add_argument("--input-file", required=True, help="Path to the input _enriched.jsonl file.")
    parser.add_argument("--db-path", default="data/chroma_db", help="Path to store the ChromaDB database.")
    parser.add_argument("--collection-name", default="university_rag", help="Name of the ChromaDB collection.")
    args = parser.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Error: Input file not found at {input_path}")
    else:
        build_index(input_path, args.db_path, args.collection_name)
