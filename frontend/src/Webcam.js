import React, { useState, useEffect, useCallback, useRef } from 'react';
import Caption from './Caption';
import Summary from './Summary';
import './Webcam.css';

const WebcamComponent = () => {
  // State management
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState(null);
  const [captionStatus, setCaptionStatus] = useState("No captions yet");
  const [caption, setCaption] = useState(null);
  const [summary, setSummary] = useState(null);
  const [backendStatus, setBackendStatus] = useState('disconnected');

  // Refs
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const pollIntervalRef = useRef(null);

  // Check backend status using fetch
  useEffect(() => {
    const checkBackendStatus = async () => {
      try {
        // Use fetch directly
        const response = await fetch('http://localhost:5000/status');
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();

        if (data.running !== undefined) {
          setBackendStatus('connected');
          setError(null);
        } else {
          // Consider if backend replies but isn't 'running' yet
          setBackendStatus('idle'); // Or 'connected but idle'
        }
      } catch (err) {
        console.error('Backend status check failed:', err);
        setBackendStatus('disconnected');
        // Optionally set an error message
        // setError('Failed to connect to the backend.');
      }
    };

    checkBackendStatus();
    const interval = setInterval(checkBackendStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  // Cleanup function for intervals
  const cleanup = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    // Also clear local stream if running
    if (streamRef.current) {
       streamRef.current.getTracks().forEach(track => track.stop());
       streamRef.current = null;
       if (videoRef.current) {
           videoRef.current.srcObject = null;
       }
    }
  }, []);

  // Poll for captions using fetch
  const pollForCaptions = useCallback(async () => {
    if (!isRunning) return;
    
    try {
      // Use fetch directly
      const response = await fetch('http://localhost:5000/caption');
       if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
      const data = await response.json();

      if (data && data.caption) {
        setCaptionStatus("Receiving captions");
        setCaption(data.caption);
        setSummary(data.summary);
      } else {
        setCaptionStatus("Waiting for captions...");
      }
    } catch (error) {
      console.error("Caption polling error:", error);
      setCaptionStatus("Error checking captions");

      // If we get a network error, update status and maybe stop polling
      if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
        setError("Lost connection to backend.");
        setIsRunning(false); // Stop the polling loop by setting isRunning to false
        setBackendStatus('disconnected');
        // No automatic reconnect attempt here to avoid potential loops
        // User would need to manually restart
      }
    }
  }, [isRunning]); // Removed startWebcam from dependencies

  // Function to update the video element with server stream
  const connectToServerStream = useCallback(() => {
    if (videoRef.current) {
      // Use the server-side video feed instead of local camera
      videoRef.current.src = 'http://localhost:5000/video_feed';
      videoRef.current.onerror = () => {
        console.error('Error loading video feed from server');
        if (videoRef.current) {
          videoRef.current.style.display = 'none';
        }
      };
    }
  }, []);

  // Start webcam using fetch
  const startWebcam = useCallback(async () => {
    setError(null);
    setCaptionStatus("Starting...");

    // Check backend status first
    if (backendStatus === 'disconnected') {
      setError('Backend is not connected. Please check if the server is running.');
      setCaptionStatus("Backend disconnected");
      return;
    }

    try {
      // Start the backend webcam process
      const startResponse = await fetch('http://localhost:5000/start', { method: 'POST' });
      if (!startResponse.ok) {
        const errorData = await startResponse.json().catch(() => ({})); // Try to get error details
        throw new Error(`Backend start failed: ${startResponse.status} ${errorData.message || ''}`);
      }
      const startData = await startResponse.json();

      if (startData.status === 'Webcam started') {
        setIsRunning(true);
        setCaptionStatus("Waiting for captions...");

        // Start polling
        pollForCaptions(); // Poll immediately
        pollIntervalRef.current = setInterval(pollForCaptions, 3000); // Then poll every 3s

        // Connect to server-side video feed
        connectToServerStream();
      } else {
        setError(`Failed to start webcam: ${startData.message || 'Unknown error'}`);
        setCaptionStatus("Start failed");
      }
    } catch (err) {
      console.error('Start webcam error:', err);
      setError(`Failed to start webcam: ${err.message}`);
      setCaptionStatus("Start error");
    }
  }, [backendStatus, pollForCaptions, connectToServerStream]);

  // Stop webcam using fetch
  const stopWebcam = useCallback(async () => {
    console.log("Stopping webcam...");
    setIsRunning(false); // Immediately update UI state
    setCaptionStatus("Stopping...");

    // Perform cleanup (stop polling, clear stream)
    cleanup();

    // Clear the video source
    if (videoRef.current) {
      videoRef.current.src = '';
    }

    // Stop the backend processing
    try {
      // Use fetch directly
      const response = await fetch('http://localhost:5000/stop', { method: 'POST' });
       if (!response.ok) {
         throw new Error(`Backend stop failed: ${response.status}`);
       }
      const data = await response.json();
      console.log("Backend stop response:", data);
      setCaptionStatus("Stopped");
      setCaption(null);
      setSummary(null);
    } catch (backendError) {
      console.error("Error stopping backend:", backendError);
      setError(`Failed to properly stop backend: ${backendError.message}`);
      setCaptionStatus("Stop error");
    }
  }, [cleanup]);

  // Manual capture using fetch
  const captureNow = useCallback(async () => {
    if (!isRunning) {
      setError("Start the camera first before capturing");
      return;
    }
    setError(null);
    setCaptionStatus("Requesting manual capture...");

    try {
      // Use fetch directly
      const response = await fetch('http://localhost:5000/capture_now', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(`Capture failed: ${response.status} ${errorData.message || ''}`);
        }
      const data = await response.json();

      if (data.status === 'success') {
        setCaption(data.caption);
        setSummary(data.summary);
        setCaptionStatus("Manual capture successful");
      } else {
        setError(`Capture failed: ${data.message || 'Unknown error'}`);
        setCaptionStatus("Manual capture failed");
      }
    } catch (err) {
      console.error('Capture error:', err);
      setError(`Failed to capture: ${err.message}`);
      setCaptionStatus("Capture error");
    }
  }, [isRunning]);

  // Clean up on unmount
  useEffect(() => {
    // This is the primary cleanup effect
    return () => {
        if (isRunning) {
            // Try to stop backend if component unmounts while running
             fetch('http://localhost:5000/stop', { method: 'POST' })
                .catch(err => console.error('Cleanup stop error:', err));
        }
      cleanup(); // Ensure streams and intervals are cleared
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRunning]); // Dependency on isRunning ensures backend stop is attempted if unmounted while running

  return (
    <div className="webcam-container">
      <div className="video-container">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className={isRunning ? "video-active" : "video-inactive"}
          aria-label="Webcam preview"
          style={{ width: '100%', height: '100%' }}
        />
        {(!isRunning || (isRunning && !videoRef.current?.src)) && (
          <div className="no-video-message">
            {isRunning ? "No video preview available but processing is running" : "Start camera to see preview"}
          </div>
        )}
      </div>

      <div className="output-section">
        <div className="output-container">
          {caption && <Caption caption={caption} />}
          {summary && <Summary summary={summary} />}
        </div>
      </div>

      <div className="controls">
        <button
          onClick={startWebcam}
          disabled={isRunning}
          aria-label="Start webcam"
          className="control-button"
        >
          Start Camera
        </button>
        <button
          onClick={stopWebcam}
          disabled={!isRunning}
          aria-label="Stop webcam"
          className="control-button"
        >
          Stop Camera
        </button>
        <button
          onClick={captureNow}
          disabled={!isRunning} // Simplified disabled state
          aria-label="Refresh capture"
          className="control-button refresh-button"
        >
          Refresh Capture
        </button>

        <div className="status-indicator">
          <span className="caption-status">Status: <span className={captionStatus.includes("Receiving") || captionStatus.includes("successful") ? "status-connected" : "status-warning"}>{captionStatus}</span></span>
        </div>
      </div>

      {error && <p className="error-message">{error}</p>}

      <div className="webcam-status">
        Backend Status: <span className={`status-${backendStatus}`}>{backendStatus}</span>
      </div>
    </div>
  );
};

export default WebcamComponent;
