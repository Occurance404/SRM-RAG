# University RAG Backend

Backend pipeline for a university-focused RAG (Retrieval-Augmented Generation) system. It crawls website content, extracts and associates text with relevant images, and indexes everything for context-aware querying. Built with Python, FastAPI, and ChromaDB.

## Architecture

The project is structured into the following main components:

- **`backend`**: The main Python application, containing the crawler, processing scripts, and the API.
  - **`api`**: FastAPI server to expose the RAG pipeline.
  - **`crawler`**: Scripts to crawl the university website.
  - **`processing`**: Scripts for chunking and enriching the crawled data.
  - **`retrieval`**: Scripts for retrieving data from the vector store.
  - **`storage`**: Scripts for managing data storage.
- **`frontend`**: A React-based frontend (currently a placeholder).
- **`data`**: Directory for storing crawled and processed data (ignored by git).

## Getting Started

### Prerequisites

- Python 3.9+
- Node.js and npm (for the frontend)

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Occurance404/SRM-RAG.git
    cd SRM-RAG
    ```

2.  **Set up the backend:**
    ```bash
    # Create and activate a virtual environment
    python -m venv rag_env
    source rag_env/bin/activate  # On Windows, use `rag_env\Scripts\activate`

    # Install backend dependencies
    pip install -r backend/requirements.txt
    ```

3.  **Set up the frontend:**
    ```bash
    cd frontend
    npm install
    ```

## Usage

1.  **Crawl the website:**
    ```bash
    python backend/crawler/crawl.py --start https://www.srmap.edu.in/ --max-pages 50 --same-domain
    ```

2.  **Process the crawled data:**
    ```bash
    python backend/processing/chunker.py --input-file data/raw/date=YYYY-MM-DD/www.srmap.edu.in.jsonl
    ```

3.  **Start the API server:**
    ```bash
    uvicorn backend.api.server:app --reload
    ```

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
