# File: main.py
import cv2
from ultralytics import YOLO
import pyttsx3
import threading
import queue
import time
import sys
import argparse

# TTS Setup
speech_queue = queue.Queue()

def tts_worker():
    """
    Worker thread for Text-to-Speech to avoid blocking the main video loop.
    """
    try:
        engine = pyttsx3.init()
        # Optional: Set properties (rate, volume, etc.)
        # engine.setProperty('rate', 150)
    except Exception as e:
        print(f"Failed to initialize TTS engine: {e}")
        return

    while True:
        text = speech_queue.get()
        if text is None:
            break
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            print(f"TTS Error: {e}")
        speech_queue.task_done()

# Start TTS Thread
tts_thread = threading.Thread(target=tts_worker, daemon=True)
tts_thread.start()

def main():
    parser = argparse.ArgumentParser(description="YOLO11 Obstacle Avoidance System")
    parser.add_argument("--url", type=str, default="http://192.168.1.100/stream", help="URL of the ESP32 MJPEG stream (e.g., http://192.168.x.x/stream)")
    args = parser.parse_args()

    # Load YOLO11 Model
    print("Loading YOLO11n model...")
    try:
        model = YOLO("yolo11n.pt")
    except Exception as e:
        print(f"Error loading model: {e}")
        sys.exit(1)

    # Connect to Stream
    print(f"Connecting to video stream at {args.url}...")
    cap = cv2.VideoCapture(args.url)

    if not cap.isOpened():
        print("Error: Could not open video stream.")
        print(f"Please check that the ESP32 is connected and the URL '{args.url}' is correct.")
        sys.exit(1)

    print("System Started. Press 'q' to quit.")

    last_speech_time = 0
    SPEECH_COOLDOWN = 3.0  # Seconds between warnings to prevent spamming
    AREA_THRESHOLD = 0.3   # Obstacle considered dangerous if it covers > 30% of the frame

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame from stream. Reconnecting...")
            time.sleep(1)
            cap.release()
            cap = cv2.VideoCapture(args.url)
            continue

        height, width, _ = frame.shape
        frame_area = height * width

        # Run Inference
        results = model(frame, verbose=False)

        detected_obstacle = False

        # Annotate Frame
        # You can use results[0].plot() for default plotting, but we need custom logic for the warning

        for result in results:
            boxes = result.boxes
            for box in boxes:
                # Get box coordinates
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                w = x2 - x1
                h = y2 - y1
                area = w * h

                # Check area ratio
                ratio = area / frame_area

                # Draw bounding box
                color = (0, 255, 0) # Green
                thickness = 2

                if ratio > AREA_THRESHOLD:
                    detected_obstacle = True
                    color = (0, 0, 255) # Red
                    thickness = 4

                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)

                # Optional: Add label
                # label = f"{model.names[int(box.cls[0])]} {box.conf[0]:.2f}"
                # cv2.putText(frame, label, (int(x1), int(y1)-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        if detected_obstacle:
            current_time = time.time()
            if current_time - last_speech_time > SPEECH_COOLDOWN:
                print("Obstacle Detected! Triggering TTS...")
                # Only put in queue if empty to ensure responsiveness
                if speech_queue.empty():
                    speech_queue.put("偵測到障礙物，請注意")
                last_speech_time = current_time

        cv2.imshow("YOLO11 Obstacle Avoidance", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Cleanup
    cap.release()
    cv2.destroyAllWindows()
    speech_queue.put(None) # Signal thread to exit
    tts_thread.join()
    print("Exited.")

if __name__ == "__main__":
    main()
