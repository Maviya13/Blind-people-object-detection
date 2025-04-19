import React, { useState, useEffect } from 'react';
import WebcamComponent from './Webcam';
import './App.css';

function App() {
  const [apiKeyWarning, setApiKeyWarning] = useState(null);
  const [backendStatus, setBackendStatus] = useState("Not connected");
  const [ttsStatus, setTtsStatus] = useState("Initializing");

  useEffect(() => {
    const checkBackendStatus = async () => {
      try {
        const response = await fetch('http://localhost:5000/status');
        const data = await response.json();
        
        // Check GROQ API key
        if (!data.groq_api_key_available) {
          setApiKeyWarning('Warning: GROQ API key not configured. Some features may be limited.');
        } else {
          setApiKeyWarning(null);
        }
        
        // Update backend status
        setBackendStatus(data.running ? "Connected and running" : "Connected but idle");
        
        // Update TTS status
        setTtsStatus(data.tts_available ? "Ready" : "Unavailable");
      } catch (error) {
        console.error('Failed to check backend status:', error);
        setBackendStatus("Connection failed");
        setTtsStatus("Unavailable");
      }
    };
    
    // Check status immediately and then every 10 seconds
    checkBackendStatus();
    const interval = setInterval(checkBackendStatus, 10000);
    
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="App">
      <header className="App-header">
        <h1>Vision Assistant</h1>
        <p className="subtitle">AI-powered visual assistance for the visually impaired</p>
      </header>
      
      {apiKeyWarning && (
        <div className="api-warning">
          {apiKeyWarning}
        </div>
      )}
      
      <div className="status-bar">
        <span className="status-item">
          Backend: <span className={backendStatus.includes("Connected") ? "status-connected" : "status-error"}>{backendStatus}</span>
        </span>
        <span className="status-item">
          TTS: <span className={ttsStatus === "Ready" ? "status-connected" : "status-warning"}>{ttsStatus}</span>
        </span>
      </div>
      
      <main className="App-main">
        <WebcamComponent />
      </main>
      
      <footer className="App-footer">
        <p>Press Start to begin visual assistance</p>
      </footer>
    </div>
  );
}

export default App;
