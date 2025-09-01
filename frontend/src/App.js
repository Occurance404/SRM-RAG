import React, { useState } from 'react';
import axios from 'axios';
import './App.css';

function App() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError('');
    setResult(null);

    try {
      // NOTE: This proxy is configured in package.json
      const response = await axios.post('http://localhost:8000/query', { query });
      setResult(response.data);
    } catch (err) {
      setError('Failed to fetch results. Please ensure the backend server is running.');
      console.error(err);
    }

    setLoading(false);
  };

  return (
    <div className="App">
      <div className="container search-container">
        <h1 className="title">🎓 University RAG Search</h1>
        <form onSubmit={handleSearch}>
          <div className="input-group mb-3">
            <input
              type="text"
              className="form-control"
              placeholder="Ask a question about the university..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button className="btn btn-primary" type="submit" disabled={loading}>
              {loading ? 'Searching...' : 'Search'}
            </button>
          </div>
        </form>

        {loading && (
          <div className="spinner-container">
            <div className="spinner-border text-primary" role="status">
              <span className="visually-hidden">Loading...</span>
            </div>
          </div>
        )}

        {error && <div className="alert alert-danger error-alert">{error}</div>}

        {result && (
          <div className="results-container">
            <div className="card">
                <div className="card-header fw-bold">Answer</div>
                <div className="card-body">
                    <p className="card-text">{result.answer}</p>
                </div>
            </div>
            
            <h4 className="mt-4">Sources</h4>
            {result.sources.map((source, index) => (
              <div className="card source-card" key={index}>
                <div className="card-body">
                  <h6 className="card-title">
                    <a href={source.url} target="_blank" rel="noopener noreferrer">
                      Source {index + 1}
                    </a>
                  </h6>
                  <p className="card-text text-muted">{source.text}</p>
                  <p className="card-text"><small className="text-muted">Relevance Score: {source.score.toFixed(4)}</small></p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;