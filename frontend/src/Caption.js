import React from 'react';
import './Caption.css';

const Caption = ({ caption }) => {
  if (!caption) return null;

  return (
    <div className="caption-container">
      <span className="caption-label">Caption:</span>
      <p className="caption-text">{caption}</p>
    </div>
  );
};

export default Caption;
