from flask import Flask, render_template, Response
import cv2
import face_recognition
import numpy as np
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import datetime
import time
import queue
import threading
import urllib.request
from dotenv import load_dotenv
from twilio.rest import Client
import os
import glob

load_dotenv('../.env')
app = Flask(__name__)

# Twilio account details
account_sid = os.getenv('account_sid')
auth_token = os.getenv('auth_token')
twilio_number = os.getenv('twilio_number')
recipient_number = os.getenv('recipient_number')
client = Client(account_sid, auth_token)

# Email configuration for alerts
SMTP_PORT = 587
SMTP_SERVER = "smtp.gmail.com"  
SENDER_EMAIL = os.getenv('SENDER_MAIL')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD')  # Use App Password for Gmail
OWNER_EMAIL = os.getenv('OWNER_EMAIL')

# ESP32-CAM stream URL
ESP32_STREAM_URL = "http://10.65.108.83" #eesp32 stream url address

# Alert cooldown settings
last_alert_time = 0
ALERT_COOLDOWN = 30
last_declare_time = 0
DECLARE_COOLDOWN = 30

# Intruder detection buffer
intruder_first_seen = None
INTRUDER_CONFIRMATION_TIME = 3  # seconds - only alert if unknown for this long
last_known_status = "Unknown"  # Track last detection status

# Face recognition settings
FACE_MATCH_TOLERANCE = 0.5  # Lower = stricter (default is 0.6)
MIN_CONFIDENCE = 0.45  # Minimum confidence for a match
PROCESS_EVERY_N_FRAMES = 3  # Process every 3rd frame (increase for better performance)
RESIZE_SCALE = 0.25  # Resize to 25% for processing (increase to 0.5 if too inaccurate)

# Known faces storage
known_face_encodings = []
known_face_names = []


def load_face_images(person_name, image_folder):
    """
    Load multiple images for a single person from a folder.
    
    Args:
        person_name: Name of the person
        image_folder: Path to folder containing their images
    
    Returns:
        Number of faces successfully loaded
    """
    loaded_count = 0
    
    # Support multiple image formats
    image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']
    image_files = []
    
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(image_folder, ext)))
    
    if not image_files:
        print(f"⚠️ No images found in {image_folder}")
        return 0
    
    print(f"📁 Loading {len(image_files)} images for {person_name}...")
    
    for img_path in image_files:
        try:
            # Load image
            img = face_recognition.load_image_file(img_path)
            
            # Get face encodings
            encodings = face_recognition.face_encodings(img)
            
            if len(encodings) > 0:
                # Use the first face found in the image
                known_face_encodings.append(encodings[0])
                known_face_names.append(person_name)
                loaded_count += 1
                print(f"  ✅ Loaded: {os.path.basename(img_path)}")
            else:
                print(f"  ❌ No face detected in: {os.path.basename(img_path)}")
                
        except Exception as e:
            print(f"  ❌ Error loading {os.path.basename(img_path)}: {e}")
    
    return loaded_count


def load_all_known_faces():
    """
    Load all known faces from the assets folder structure:
    
      Owner1_imgs/
        photo1.jpg
        photo2.jpg
        ...
    """
    base_path = "../assets"
    
    # Define your owners and their folders
    owners = {
        "Owner1_name": os.path.join(base_path, "Owner_imgs")
    }
    
    total_loaded = 0
    
    for person_name, folder_path in owners.items():
        if os.path.exists(folder_path):
            count = load_face_images(person_name, folder_path)
            total_loaded += count
            print(f"✅ Loaded {count} images for {person_name}\n")
        else:
            print(f"⚠️ Folder not found: {folder_path}\n")
    
    print(f"🎯 Total faces loaded: {total_loaded}")
    return total_loaded


# Load all known faces at startup
print("=" * 50)


def send_email_alert(image_path, subject, body):
    """
    Send email with intruder photo attachment.
    
    Args:
        image_path: Path to the intruder image
        subject: Email subject
        body: Email body text
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = OWNER_EMAIL
        msg['Subject'] = subject
        
        # Add body text
        msg.attach(MIMEText(body, 'plain'))
        
        # Attach image
        with open(image_path, 'rb') as f:
            img_data = f.read()
            image = MIMEImage(img_data, name=os.path.basename(image_path))
            msg.attach(image)
        
        # Send email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  # Enable encryption
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        
        print(f"📧 Email sent successfully to {OWNER_EMAIL}")
        return True
        
    except Exception as e:
        print(f"❌ Email sending failed: {e}")
        return False
print("LOADING KNOWN FACES")
print("=" * 50)
load_all_known_faces()
print("=" * 50)


def recognize_face(face_encoding):
    """
    Recognize a face with improved accuracy using voting mechanism.
    
    Args:
        face_encoding: The face encoding to identify
    
    Returns:
        tuple: (name, confidence_score)
    """
    if len(known_face_encodings) == 0:
        return "Unknown", 0.0
    
    # Calculate distances to all known faces
    face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
    
    # Get all matches within tolerance
    matches = face_distances <= FACE_MATCH_TOLERANCE
    
    if not any(matches):
        return "Unknown", 0.0
    
    # Use voting: count matches per person
    matched_names = [known_face_names[i] for i, match in enumerate(matches) if match]
    
    if not matched_names:
        return "Unknown", 0.0
    
    # Count votes for each name
    from collections import Counter
    vote_counts = Counter(matched_names)
    
    # Get the winner
    winner_name, vote_count = vote_counts.most_common(1)[0]
    
    # Calculate confidence based on:
    # 1. Number of votes
    # 2. Average distance of matching faces
    matching_distances = [face_distances[i] for i, name in enumerate(known_face_names) 
                         if name == winner_name and matches[i]]
    
    avg_distance = np.mean(matching_distances)
    confidence = 1.0 - avg_distance  # Convert distance to confidence
    
    # Require minimum votes and confidence
    total_images_for_person = known_face_names.count(winner_name)
    vote_ratio = vote_count / total_images_for_person
    
    # Final confidence combines distance and vote ratio
    final_confidence = (confidence * 0.7) + (vote_ratio * 0.3)
    
    if final_confidence < MIN_CONFIDENCE:
        return "Unknown", final_confidence
    
    return winner_name, final_confidence


def generate_frames():
    global last_alert_time, ALERT_COOLDOWN
    global last_declare_time, DECLARE_COOLDOWN
    global intruder_first_seen, INTRUDER_CONFIRMATION_TIME, last_known_status
    global ESP32_STREAM_URL
    
    stream_url = ESP32_STREAM_URL + ":81/stream"
    print(f"Connecting to ESP32 stream at {stream_url} ...")

    try:
        stream = urllib.request.urlopen(stream_url, timeout=5)
    except urllib.error.URLError as e:
        print(f"❌ Failed to connect to ESP32 stream: {e}")
        return
    
    bytes_data = b''
    frame_count = 0
    
    # Cache for last detection result (to display on non-processed frames)
    last_face_results = []  # Store (top, right, bottom, left, name, confidence)

    while True:
        bytes_data += stream.read(1024)
        a = bytes_data.find(b'\xff\xd8')  # JPEG start
        b = bytes_data.find(b'\xff\xd9')  # JPEG end
        
        if a != -1 and b != -1:
            jpg = bytes_data[a:b+2]
            bytes_data = bytes_data[b+2:]

            if len(jpg) < 1000:
                continue

            frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue

            frame_count += 1
            current_time = time.time()
            
            # Only process face recognition every N frames
            if frame_count % PROCESS_EVERY_N_FRAMES == 0:
                # Resize for speed
                small_frame = cv2.resize(frame, (0, 0), fx=RESIZE_SCALE, fy=RESIZE_SCALE)
                rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                rgb_small_frame = np.ascontiguousarray(rgb_small_frame, dtype=np.uint8)

                try:
                    # Face detection with faster model
                    face_locations = face_recognition.face_locations(rgb_small_frame, model="hog", number_of_times_to_upsample=1)
                    
                    face_detected_this_frame = False
                    last_face_results = []  # Clear old results
                    
                    if len(face_locations) > 0:
                        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations, num_jitters=1)
                        
                        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                            face_detected_this_frame = True
                            
                            # Use improved recognition
                            name, confidence = recognize_face(face_encoding)
                            
                            # Scale coordinates back
                            scale_factor = int(1 / RESIZE_SCALE)
                            top *= scale_factor
                            right *= scale_factor
                            bottom *= scale_factor
                            left *= scale_factor
                            
                            # Store results for display on all frames
                            last_face_results.append((top, right, bottom, left, name, confidence))

                            # Handle unknown person with confirmation delay
                            if name == "Unknown":
                                if intruder_first_seen is None:
                                    intruder_first_seen = current_time
                                    print(f"⚠️ Unknown person detected. Monitoring for {INTRUDER_CONFIRMATION_TIME} seconds...")
                                
                                time_as_intruder = current_time - intruder_first_seen
                                
                                if time_as_intruder >= INTRUDER_CONFIRMATION_TIME:
                                    if current_time - last_alert_time > ALERT_COOLDOWN:
                                        print(f"🚨 INTRUDER CONFIRMED after {time_as_intruder:.1f}s!")
                                        
                                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                        intruder_filename = f"intruder_{timestamp}.jpg"
                                        cv2.imwrite(intruder_filename, frame)
                                        print(f"📸 Intruder photo saved: {intruder_filename}")
                                        
                                        try:
                                            message = client.messages.create(
                                                body='⚠️ Intruder Detected!!\nEntry Denied\nCheck your email for photo.',
                                                from_=twilio_number,
                                                to=recipient_number
                                            )
                                            print(f"📱 SMS alert sent: {message.sid}")
                                        except Exception as e:
                                            print(f"❌ SMS failed: {e}")
                                        
                                        email_subject = f"🚨 Security Alert: Intruder Detected - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                                        email_body = f"""
Security Alert!

An unrecognized person was detected at your door.

Detection Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Confirmation Time: {time_as_intruder:.1f} seconds
Status: Entry Denied

Please find the attached photo of the intruder.

This is an automated message from your Smart Door Security System.
"""
                                        send_email_alert(intruder_filename, email_subject, email_body)
                                        
                                        last_alert_time = current_time
                                        last_known_status = "Unknown"
                            
                            else:
                                if intruder_first_seen is not None:
                                    print(f"✅ Owner recognized. Cancelling intruder alert.")
                                intruder_first_seen = None
                                
                                if current_time - last_declare_time > DECLARE_COOLDOWN:
                                    print(f"✅ Owner: {name} Detected! (Confidence: {confidence*100:.1f}%)")
                                    
                                    try:
                                        message = client.messages.create(
                                            body=f'✅ {name} Detected!\nAccess Granted',
                                            from_=twilio_number,
                                            to=recipient_number
                                        )
                                        print(f"📱 Notification sent: {message.sid}")
                                    except Exception as e:
                                        print(f"❌ SMS failed: {e}")
                                    
                                    last_declare_time = current_time
                                    last_known_status = name
                    
                    if not face_detected_this_frame:
                        if intruder_first_seen is not None:
                            print("ℹ️ Face lost. Resetting intruder timer.")
                        intruder_first_seen = None

                except Exception as e:
                    print(f"❌ Face processing error: {e}")
            
            # Draw boxes on EVERY frame using cached results (smooth display)
            for top, right, bottom, left, name, confidence in last_face_results:
                color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
                cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                
                label = f"{name} ({confidence*100:.1f}%)"
                cv2.putText(frame, label, (left, top - 10), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                # Show countdown for intruders
                if name == "Unknown" and intruder_first_seen is not None:
                    time_elapsed = current_time - intruder_first_seen
                    if time_elapsed < INTRUDER_CONFIRMATION_TIME:
                        countdown = INTRUDER_CONFIRMATION_TIME - time_elapsed
                        warning_text = f"Verifying... {countdown:.1f}s"
                        cv2.putText(frame, warning_text, (left, bottom + 25), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)

            # Resize and encode frame for streaming
            frame = cv2.resize(frame, (640, 480))
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            frame = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame',
                    headers={"Cache-Control": "no-cache"})


if __name__ == '__main__':
    app.run(debug=True, threaded=True)