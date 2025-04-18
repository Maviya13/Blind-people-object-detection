import React, { useState, useEffect } from 'react';
import axios from 'axios';

const Caption = () => {
  const [caption, setCaption] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchCaption = async () => {
      try {
        const res = await axios.get("http://localhost:5000/caption");
        setCaption(res.data.caption);
        setError(null);
      } catch (error) {
        console.error(error);
        setError("Failed to fetch caption");
      } finally {
        setLoading(false);
      }
    };

    const interval = setInterval(fetchCaption, 5000);
    fetchCaption(); // Initial fetch

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="caption-container" aria-live="polite">
      <h2>Live Caption</h2>
      {loading ? (
        <p className="loading">Loading caption...</p>
      ) : error ? (
        <p className="error">{error}</p>
      ) : (
        <p className="caption-text">{caption || "No caption available"}</p>
      )}
    </div>
  );
};

export default Caption;
