# backend/app.py

from flask import Flask, jsonify, request
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

app = Flask(__name__)
CORS(app)

# Load BLIP model
processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")

# Groq setup
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # Set in .env
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json"
}

# TTS setup
engine = pyttsx3.init()
engine.setProperty('rate', 150)

# Global state
running = False
latest_caption = ""
latest_summary = ""

def get_summary_from_groq(caption):
    prompt = f"""
You are a vision AI assistant. Expand this basic image caption into a full scene summary describing setting, people, objects, mood, and context.

Caption: "{caption}"
"""
    response = requests.post(GROQ_ENDPOINT, headers=HEADERS, json={
        "model": "mixtral-8x7b-32768",
        "messages": [{"role": "user", "content": prompt}]
    })

    if response.status_code == 200:
        return response.json()['choices'][0]['message']['content']
    return "Groq summarization failed."

def webcam_loop():
    global running, latest_caption, latest_summary
    cap = cv2.VideoCapture(0)
    while running:
        ret, frame = cap.read()
        if not ret:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        inputs = processor(images=img, return_tensors="pt")
        output = model.generate(**inputs)
        caption = processor.decode(output[0], skip_special_tokens=True)
        latest_caption = caption
        latest_summary = get_summary_from_groq(caption)
        engine.say(latest_summary)
        engine.runAndWait()
        time.sleep(5)
    cap.release()

@app.route('/start', methods=['POST'])
def start():
    global running
    if not running:
        running = True
        threading.Thread(target=webcam_loop).start()
        return jsonify({"status": "Webcam started"}), 200
    return jsonify({"status": "Already running"}), 400

@app.route('/stop', methods=['POST'])
def stop():
    global running
    running = False
    return jsonify({"status": "Webcam stopped"}), 200

@app.route('/caption', methods=['GET'])
def caption():
    return jsonify({
        "caption": latest_caption,
        "summary": latest_summary
    })

if __name__ == '__main__':
    app.run(debug=True)
