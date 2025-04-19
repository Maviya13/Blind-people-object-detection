# backend/app.py

from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
import threading
import cv2
import time
from PIL import Image
import torch
from transformers import BlipProcessor, BlipForConditionalGeneration
import pyttsx3
import requests
import os
import logging
import dotenv
import numpy as np
import queue
import sys
import traceback

# Load environment variables
dotenv.load_dotenv()

# Configure logging with both file and console output
log_file = 'app.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

app = Flask(__name__)
CORS(app)

# Disable debug mode and auto-reloader for stability
app.config['DEBUG'] = False
app.config['ENV'] = 'production'

# Configure upload folder and ensure it exists with proper permissions
try:
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    logging.info(f"Upload directory configured: {app.config['UPLOAD_FOLDER']}")
except Exception as e:
    logging.error(f"Error configuring upload directory: {e}")
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    logging.warning(f"Using fallback upload directory: {app.config['UPLOAD_FOLDER']}")

# Configure Flask to serve files from the uploads directory
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Load BLIP model
processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base", use_fast=True)
model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")

# Groq setup
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # Set in .env
logging.info(f"GROQ API KEY available: {bool(GROQ_API_KEY)}, Key starts with: {GROQ_API_KEY[:5] if GROQ_API_KEY else 'None'}")
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json"
}

# Global variables for TTS and camera
tts_engine = None
camera = None
frame_queue = queue.Queue(maxsize=30)  # Limited size queue for frames
caption_queue = queue.Queue(maxsize=10)  # Queue for captions
latest_caption = ""
latest_summary = ""
running = False

# Locks for thread safety
caption_lock = threading.Lock()
summary_lock = threading.Lock()
running_lock = threading.Lock()
queue_lock = threading.Lock()  # Lock for the frame queue

# Constants
CAMERA_BACKENDS = [
    (cv2.CAP_DSHOW, "DirectShow"),
    (cv2.CAP_MSMF, "Media Foundation"),
    (cv2.CAP_ANY, "Auto-detect")
]
MAX_FRAME_AGE = 5  # Maximum age of frame in seconds
MIN_CAPTION_INTERVAL = 5  # Minimum seconds between captions
MAX_RETRIES = 3  # Maximum number of retries for operations
MODEL_PATH = "Salesforce/blip-image-captioning-base"

class CameraManager:
    def __init__(self):
        self.camera = None
        self.backend = None
        self.last_frame_time = 0
        self.frame_count = 0
        self.fps = 0
        self.initialized = False
        self.target_fps = 30
        self.fps_improvement_attempts = 0
        self.max_fps_attempts = 3
        
    def initialize(self):
        """Initialize camera with multiple backends and verification"""
        if self.initialized:
            return True
            
        for backend, name in CAMERA_BACKENDS:
            try:
                if self.camera is not None:
                    self.camera.release()
                    time.sleep(0.5)
                
                self.camera = cv2.VideoCapture(0, backend)
                if not self.camera.isOpened():
                    logging.warning(f"Failed to open camera with {name}")
                    continue
                
                # Set camera properties for better performance
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.camera.set(cv2.CAP_PROP_FPS, self.target_fps)
                self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                # Test frame capture with multiple attempts
                for _ in range(3):
                    ret, frame = self.camera.read()
                    if ret and frame is not None:
                        self.backend = name
                        self.initialized = True
                        logging.info(f"Successfully initialized camera with {name}")
                        return True
                    time.sleep(0.1)
                
                logging.warning(f"Failed to capture test frame with {name}")
                self.camera.release()
                
            except Exception as e:
                logging.error(f"Error initializing camera with {name}: {e}")
                if self.camera is not None:
                    self.camera.release()
                    self.camera = None
        
        return False
    
    def read_frame(self):
        """Read a frame with error handling and FPS calculation"""
        if not self.initialized or self.camera is None or not self.camera.isOpened():
            if not self.initialize():
                return None, None
        
        try:
            current_time = time.time()
            
            # Skip frames if we're running too fast
            if current_time - self.last_frame_time < 1.0/self.target_fps:
                time.sleep(0.001)  # Small sleep to prevent CPU overload
                return None, None
            
            ret, frame = self.camera.read()
            if not ret or frame is None:
                logging.error("Failed to capture frame")
                self.initialized = False  # Force reinitialization
                return None, None
            
            # Calculate FPS
            self.frame_count += 1
            if current_time - self.last_frame_time >= 1.0:
                self.fps = self.frame_count
                self.frame_count = 0
                self.last_frame_time = current_time
                
                # Only try to improve FPS a limited number of times
                if self.fps < self.target_fps * 0.5 and self.fps_improvement_attempts < self.max_fps_attempts:
                    logging.warning(f"Camera FPS too low: {self.fps}, attempting to improve... (Attempt {self.fps_improvement_attempts + 1}/{self.max_fps_attempts})")
                    self.camera.set(cv2.CAP_PROP_FPS, self.target_fps)
                    self.fps_improvement_attempts += 1
                elif self.fps_improvement_attempts >= self.max_fps_attempts:
                    logging.info(f"Camera running at {self.fps} FPS after {self.max_fps_attempts} improvement attempts")
                else:
                    logging.info(f"Camera FPS: {self.fps}")
            
            # Resize frame for processing
            frame = cv2.resize(frame, (640, 480))
            return frame, current_time
            
        except Exception as e:
            logging.error(f"Error reading frame: {e}")
            self.initialized = False
            return None, None
    
    def release(self):
        """Release camera resources"""
        if self.camera is not None:
            self.camera.release()
            self.camera = None
        self.initialized = False

class TTSManager:
    def __init__(self):
        self.engine = None
        self.initialized = False
        self.last_speak_time = 0
        self.min_speak_interval = 5
        self.voice_id = None
        
    def initialize(self):
        """Initialize TTS engine with retry mechanism"""
        if self.initialized and self.engine is not None:
            return True
            
        for attempt in range(MAX_RETRIES):
            try:
                if self.engine is not None:
                    try:
                        self.engine.stop()
                    except:
                        pass
                    self.engine = None
                
                self.engine = pyttsx3.init()
                voices = self.engine.getProperty('voices')
                
                if not voices:
                    logging.error("No TTS voices found")
                    continue
                
                # Set English voice
                english_voice = None
                for voice in voices:
                    if "english" in voice.name.lower():
                        english_voice = voice
                        break
                
                if english_voice:
                    self.voice_id = english_voice.id
                    self.engine.setProperty('voice', self.voice_id)
                    logging.info(f"Set English voice: {english_voice.name}")
                
                # Set properties
                self.engine.setProperty('rate', 150)
                self.engine.setProperty('volume', 1.0)
                
                # Test TTS
                self.engine.say("TTS initialized")
                self.engine.runAndWait()
                
                self.initialized = True
                logging.info("TTS initialization successful")
                return True
                
            except Exception as e:
                logging.error(f"TTS initialization attempt {attempt + 1} failed: {e}")
                time.sleep(1)
        
        return False
    
    def speak(self, text):
        """Speak text with rate limiting and error handling"""
        if not text or not text.strip():
            return False
            
        if not self.initialized or not self.engine:
            if not self.initialize():
                return False
        
        current_time = time.time()
        if current_time - self.last_speak_time < self.min_speak_interval:
            return False
        
        try:
            # Clean text for better speech
            clean_text = text.strip()
            clean_text = clean_text.replace("a person", "someone")
            clean_text = clean_text.replace("a man", "someone")
            clean_text = clean_text.replace("a woman", "someone")
            
            self.engine.say(clean_text)
            self.engine.runAndWait()
            self.last_speak_time = current_time
            return True
            
        except Exception as e:
            logging.error(f"Error speaking text: {e}")
            self.initialized = False
            return False

def initialize_model():
    """Initialize BLIP model with error handling"""
    global processor, model
    try:
        if processor is not None and model is not None:
            return True
            
        logging.info("Initializing BLIP model...")
        processor = BlipProcessor.from_pretrained(MODEL_PATH)
        model = BlipForConditionalGeneration.from_pretrained(MODEL_PATH)
        
        # Test model
        test_image = Image.new('RGB', (100, 100), color='white')
        inputs = processor(images=test_image, return_tensors="pt")
        output = model.generate(**inputs, max_length=20)
        processor.decode(output[0], skip_special_tokens=True)
        
        logging.info("BLIP model initialized successfully")
        return True
    except Exception as e:
        logging.error(f"Error initializing BLIP model: {e}")
        traceback.print_exc()
        return False

def generate_caption(frame):
    """Generate caption with improved validation"""
    try:
        if frame is None or not isinstance(frame, np.ndarray):
            return None
        
        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame_rgb)
        
        # Process image
        inputs = processor(images=image, return_tensors="pt")
        output = model.generate(
            **inputs,
            max_length=50,
            num_beams=5,
            early_stopping=True,
            no_repeat_ngram_size=2,  # Prevent repetition
            length_penalty=1.0,  # Balanced length
            repetition_penalty=1.5  # Prevent repetitive words
        )
        
        caption = processor.decode(output[0], skip_special_tokens=True)
        
        # Validate caption
        if not caption or len(caption.strip()) < 10:
            logging.warning(f"Generated invalid caption: {caption}")
            return None
        
        logging.info(f"Generated caption: {caption}")
        return caption
        
    except Exception as e:
        logging.error(f"Error generating caption: {e}")
        traceback.print_exc()
        return None

def capture_frames():
    """Capture frames with improved error handling"""
    global running
    camera_manager = CameraManager()
    
    if not camera_manager.initialize():
        logging.error("Failed to initialize camera")
        running = False  # Stop the system if camera fails
        return
    
    consecutive_failures = 0
    while running:
        try:
            frame, timestamp = camera_manager.read_frame()
            if frame is None:
                consecutive_failures += 1
                if consecutive_failures > 10:
                    logging.error("Too many consecutive frame capture failures")
                    running = False  # Stop the system if camera fails
                    break
                time.sleep(0.1)
                continue
            
            consecutive_failures = 0
            
            # Add frame to queue
            try:
                frame_queue.put((frame, timestamp), block=False)
            except queue.Full:
                try:
                    frame_queue.get_nowait()
                    frame_queue.put((frame, timestamp))
                except:
                    pass
            
            # Maintain target FPS
            time.sleep(1.0/camera_manager.target_fps)
            
        except Exception as e:
            logging.error(f"Error in capture loop: {e}")
            traceback.print_exc()
            time.sleep(0.1)
    
    camera_manager.release()

def process_frames():
    """Process frames with improved caption generation"""
    global running
    last_caption_time = 0
    prev_captions = []
    consecutive_failures = 0
    
    logging.info("Process Thread: Starting caption generation...")
    
    while running:
        try:
            current_time = time.time()
            
            # Get latest frame
            try:
                frame, timestamp = frame_queue.get_nowait()
            except queue.Empty:
                time.sleep(0.1)
                continue
            
            # Check frame age
            if current_time - timestamp > MAX_FRAME_AGE:
                continue
            
            # Check caption interval
            if current_time - last_caption_time < MIN_CAPTION_INTERVAL:
                continue
            
            # Generate caption
            logging.info("Process Thread: Generating caption...")
            caption = generate_caption(frame)
            if not caption:
                consecutive_failures += 1
                if consecutive_failures > 5:
                    logging.error("Too many consecutive caption generation failures")
                    time.sleep(1)
                continue
            
            consecutive_failures = 0
            logging.info(f"Process Thread: Generated caption: {caption}")
            
            # Check similarity with previous captions
            is_similar = False
            for prev_caption in prev_captions:
                if similar_captions(caption, prev_caption):
                    is_similar = True
                    logging.info(f"Process Thread: Skipping similar caption: {caption}")
                    break
            
            if not is_similar:
                # Update caption history
                prev_captions.append(caption)
                if len(prev_captions) > 5:
                    prev_captions.pop(0)
                
                # Add caption to queue
                try:
                    caption_queue.put((caption, current_time), block=False)
                    logging.info(f"Process Thread: Added caption to queue: {caption}")
                except queue.Full:
                    try:
                        caption_queue.get_nowait()
                        caption_queue.put((caption, current_time))
                    except:
                        pass
                
                last_caption_time = current_time
            
        except Exception as e:
            logging.error(f"Error in process loop: {e}")
            traceback.print_exc()
            time.sleep(0.1)

def speak_captions():
    """Speak captions with improved TTS management"""
    global running
    tts_manager = TTSManager()
    last_spoken = ""
    consecutive_failures = 0
    
    logging.info("TTS Thread: Starting...")
    
    while running:
        try:
            # Get latest caption
            try:
                caption, timestamp = caption_queue.get_nowait()
            except queue.Empty:
                time.sleep(0.1)
                continue
            
            # Check if caption is new
            if caption != last_spoken:
                logging.info(f"TTS Thread: Speaking caption: {caption}")
                if tts_manager.speak(caption):
                    last_spoken = caption
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    if consecutive_failures > 3:
                        logging.error("Too many consecutive TTS failures")
                        time.sleep(1)
            
        except Exception as e:
            logging.error(f"Error in TTS loop: {e}")
            traceback.print_exc()
            time.sleep(0.1)

def get_summary_from_groq(caption):
    logging.info(f"Requesting summary from Groq for caption: {caption}")
    
    # First, generate a simple summary as fallback
    fallback_summary = f"Scene contains {caption}. The image appears to show {caption}, which likely includes the main subjects or objects in frame."
    
    # If no GROQ API key or it's invalid, use fallback directly
    if not GROQ_API_KEY:
        logging.warning("No GROQ API key available, using fallback summary")
        return fallback_summary
    
    prompt = f"""
You are a vision AI assistant. Expand this basic image caption into a full scene summary describing setting, people, objects, mood, and context.

Caption: "{caption}"
"""
    try:
        # Use current available Groq model (as of April 2025)
        response = requests.post(GROQ_ENDPOINT, headers=HEADERS, json={
            "model": "llama3-70b-8192",  # Updated to a current model
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 200,
            "top_p": 1,
            "stream": False
        })
        
        if response.status_code == 200:
            summary = response.json()['choices'][0]['message']['content']
            logging.info(f"Received summary from Groq: {summary[:50]}...")
            return summary
        else:
            logging.error(f"Groq API error: {response.status_code} - {response.text}")
            # Use fallback local summary instead
            return fallback_summary
    except Exception as e:
        logging.error(f"Exception in get_summary_from_groq: {str(e)}")
        return fallback_summary

# Helper function to check if captions are similar
def similar_captions(caption1, caption2, threshold=0.5):
    # More sophisticated similarity check
    words1 = set(caption1.lower().split())
    words2 = set(caption2.lower().split())
    
    if not words1 or not words2:
        return False
        
    # Remove common stop words
    stop_words = {'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
    words1 = words1 - stop_words
    words2 = words2 - stop_words
    
    if not words1 or not words2:
        return False
        
    common_words = words1.intersection(words2)
    similarity = len(common_words) / min(len(words1), len(words2))
    
    return similarity > threshold

# Main webcam control function
def webcam_loop():
    global running
    logging.info("Starting webcam system")
    
    # Start capture thread
    capture_thread = threading.Thread(target=capture_frames)
    capture_thread.daemon = True
    capture_thread.start()
    
    # Start processing thread
    process_thread = threading.Thread(target=process_frames)
    process_thread.daemon = True
    process_thread.start()
    
    # Start TTS thread
    tts_thread = threading.Thread(target=speak_captions)
    tts_thread.daemon = True
    tts_thread.start()
    
    logging.info("All threads started")

@app.route('/start', methods=['POST'])
def start():
    """Start the webcam system"""
    global running
    
    if running:
        return jsonify({"status": "Already running"}), 200
    
    # Initialize components
    if not initialize_model():
        return jsonify({"status": "Error", "message": "Failed to initialize model"}), 500
    
    # Start threads
    running = True
    logging.info("Starting capture thread...")
    threading.Thread(target=capture_frames, daemon=True).start()
    time.sleep(0.5)  # Give camera time to initialize
    
    logging.info("Starting process thread...")
    threading.Thread(target=process_frames, daemon=True).start()
    
    logging.info("Starting TTS thread...")
    threading.Thread(target=speak_captions, daemon=True).start()
    
    return jsonify({"status": "Started"}), 200

@app.route('/stop', methods=['POST'])
def stop():
    """Stop the webcam system"""
    global running, camera
    
    running = False
    if camera is not None:
        camera.release()
        camera = None
    
    return jsonify({"status": "Stopped"}), 200

@app.route('/caption', methods=['GET'])
def caption():
    # Thread-safe access to global variables
    with caption_lock:
        current_caption = latest_caption
    with summary_lock:
        current_summary = latest_summary
    
    # Log only if caption or summary is available to reduce noise
    if current_caption or current_summary:
        logging.info(f"Caption endpoint called. Returning: caption={current_caption[:30]}..., summary={current_summary[:30]}...")

    return jsonify({
        "caption": current_caption,
        "summary": current_summary
    })

# Verify BLIP model is working
def verify_model():
    try:
        logging.info("Initializing BLIP model")
        # Just check if the model and processor are loaded
        if model is None or processor is None:
            logging.error("BLIP model or processor not initialized")
            return False, "Model not initialized"
            
        logging.info("BLIP model initialized successfully")
        return True, "Model initialized"
    except Exception as e:
        logging.error(f"Failed to initialize model: {str(e)}")
        return False, str(e)

@app.route('/status', methods=['GET'])
def status():
    """Diagnostic endpoint check"""
    global tts_engine
    
    with running_lock:
        is_running = running
    
    with caption_lock:
        has_caption = bool(latest_caption)
    
    with summary_lock:
        has_summary = bool(latest_summary)
    
    # Check TTS availability
    tts_available = tts_engine is not None
    tts_status = "ready" if tts_available else "unavailable"
    tts_details = "TTS engine initialized" if tts_available else "TTS engine not initialized"
    
    status_info = {
        "running": is_running,
        "latest_caption_available": has_caption,
        "latest_summary_available": has_summary,
        "groq_api_key_available": bool(GROQ_API_KEY),
        "tts_available": tts_available,
        "tts_status": tts_status,
        "tts_details": tts_details
    }
    
    return jsonify(status_info)

@app.route('/capture_now', methods=['POST'])
def capture_now():
    global latest_caption, latest_summary
    
    try:
        with queue_lock:
            if not frame_queue:
                return jsonify({
                    'status': 'error',
                    'message': 'No frames available'
                }), 400
                
            # Get the most recent frame
            frame, _ = frame_queue[-1]
            
            # Generate caption
            caption = generate_caption(frame)
            if not caption:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to generate caption'
                }), 500
                
            # Generate summary
            summary = get_summary_from_groq(caption)
            
            # Update latest caption and summary
            with caption_lock:
                latest_caption = caption
                latest_summary = summary
                
            return jsonify({
                'status': 'success',
                'caption': caption,
                'summary': summary
            })
        
    except Exception as e:
        logging.error(f"Capture error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/video_feed')
def video_feed():
    """Stream video feed"""
    def generate():
        while running:
            try:
                frame, _ = frame_queue.get(timeout=1.0)
                ret, buffer = cv2.imencode('.jpg', frame)
                if not ret:
                    continue
                
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n'
                       b'\r\n' + frame_bytes + b'\r\n')
                
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Error in video feed: {e}")
                traceback.print_exc()
                continue
    
    return Response(generate(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/caption', methods=['GET'])
def get_caption():
    """Get latest caption"""
    try:
        caption, _ = caption_queue.get_nowait()
        return jsonify({"caption": caption}), 200
    except queue.Empty:
        return jsonify({"caption": None}), 200

if __name__ == '__main__':
    # Run the Flask app without debug mode
    # Use a production-ready WSGI server like waitress or gunicorn in a real deployment
    # Example: waitress-serve --host 127.0.0.1 --port 5000 app:app
    app.run(host='127.0.0.1', port=5000, debug=False)
