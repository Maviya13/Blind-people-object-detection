import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const Webcam = () => {
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState(null);
  const videoRef = useRef(null);

  const startWebcam = async () => {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      await axios.post("http://localhost:5000/start");
      setIsRunning(true);
    } catch (error) {
      console.error(error);
      setError("Failed to access webcam. Please ensure your camera is connected and permissions are granted.");
    }
  };

  const stopWebcam = async () => {
    try {
      if (videoRef.current && videoRef.current.srcObject) {
        const tracks = videoRef.current.srcObject.getTracks();
        tracks.forEach(track => track.stop());
      }
      await axios.post("http://localhost:5000/stop");
      setIsRunning(false);
    } catch (error) {
      console.error(error);
      setError("Failed to stop webcam.");
    }
  };

  useEffect(() => {
    return () => {
      stopWebcam();
    };
  }, []);

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
        />
      </div>
      <div className="controls">
        <button
          onClick={startWebcam}
          disabled={isRunning}
          aria-label="Start webcam"
        >
          Start Camera
        </button>
        <button
          onClick={stopWebcam}
          disabled={!isRunning}
          aria-label="Stop webcam"
        >
          Stop Camera
        </button>
      </div>
      {error && <p className="error-message">{error}</p>}
    </div>
  );
};

export default Webcam;
