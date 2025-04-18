import React from 'react';
import Webcam from './Webcam';
import Caption from './Caption';
import Summary from './Summary';
import './App.css';

function App() {
  return (
    <div className="App">
      <header className="App-header">
        <h1>Vision Assistant</h1>
        <p className="subtitle">AI-powered visual assistance for the visually impaired</p>
      </header>
      <main className="App-main">
        <section className="webcam-section">
          <Webcam />
        </section>
        <section className="output-section">
          <div className="output-container">
            <Caption />
            <Summary />
          </div>
        </section>
      </main>
      <footer className="App-footer">
        <p>Press Start to begin visual assistance</p>
      </footer>
    </div>
  );
}

export default App;
