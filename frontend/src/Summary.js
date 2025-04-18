import React, { useState, useEffect } from 'react';
import axios from 'axios';

const Summary = () => {
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchSummary = async () => {
      try {
        const res = await axios.get("http://localhost:5000/caption");
        setSummary(res.data.summary);
        setError(null);
      } catch (error) {
        console.error(error);
        setError("Failed to fetch summary");
      } finally {
        setLoading(false);
      }
    };

    const interval = setInterval(fetchSummary, 5000);
    fetchSummary(); // Initial fetch

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="summary-container" aria-live="polite">
      <h2>Scene Summary</h2>
      {loading ? (
        <p className="loading">Generating summary...</p>
      ) : error ? (
        <p className="error">{error}</p>
      ) : (
        <p className="summary-text">{summary || "No summary available"}</p>
      )}
    </div>
  );
};

export default Summary;
