import React from 'react';
import './Summary.css';

const Summary = ({ summary }) => {
  if (!summary) return null;

  return (
    <div className="summary-container">
      <span className="summary-label">Summary:</span>
      <p className="summary-text">{summary}</p>
    </div>
  );
};

export default Summary;
