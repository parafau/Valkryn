import cv2
import face_recognition
import numpy as np
from datetime import datetime
import time
import queue
import threading
from twilio.rest import Client
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from dotenv import load_dotenv
import os

load_dotenv('../.env')

account_sid = os.getenv('account_sid')
auth_token = os.getenv('auth_token')
twilio_number = os.getenv('twilio_number')
recipient_number = os.getenv('recipient_number')

# Create Twilio client
client = Client(account_sid, auth_token)

# Email configuration for alerts
SMTP_PORT = 587
SMTP_SERVER = "smtp.gmail.com"  
SENDER_EMAIL = os.getenv('SENDER_MAIL')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD')  # Use App Password for Gmail
OWNER_EMAIL = os.getenv('OWNER_EMAIL')

# ESP32-CAM stream URL
ESP32_STREAM_URL = "http://10.140.14.83"  # change to your IP

# Add error handling and alert cooldown
last_alert_time = 0
ALERT_COOLDOWN = 30
DECLARE_COOLDOWN = 30  # seconds between alerts
last_declare_time = 0

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

# Load known faces
known_face_encodings = []
known_face_names = []

# Example: add owner's photo
try:
    owner_img = face_recognition.load_image_file(r"../assets/img1.jpg")
    owner_encodings = face_recognition.face_encodings(owner_img)
    if len(owner_encodings) > 0:
        known_face_encodings.append(owner_encodings[0])
        known_face_names.append("Owner1")

    else:
        print("No face found in owner image!")
except FileNotFoundError:
    print("Owner image not found!")

try:
    owner_img = face_recognition.load_image_file(r"../assets/img2.jpg")
    owner_encodings = face_recognition.face_encodings(owner_img)
    if len(owner_encodings) > 0:
        known_face_encodings.append(owner_encodings[0])
        known_face_names.append("Owner2")

    else:
        print("No face found in owner image!")
except FileNotFoundError:
    print("Owner image not found!")

# Start video stream
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce latency

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to grab frame")
        break

    # Resize for speed - but ensure proper data type
    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)  # Proper color conversion
    
    # Ensure the array is contiguous and uint8
    rgb_small_frame = np.ascontiguousarray(rgb_small_frame, dtype=np.uint8)

    try:
        # Face detection
        face_locations = face_recognition.face_locations(rgb_small_frame)
        print(f"Found {len(face_locations)} faces") 
        
        if len(face_locations) > 0:
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
            print(f"Generated {len(face_encodings)} encodings")
            
            for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
                name = "Unknown"

                if len(known_face_encodings) > 0:
                    face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                    best_match = np.argmin(face_distances)
                    if matches[best_match]:
                        name = known_face_names[best_match]

                # Scale coordinates back to original frame size
                top *= 4
                right *= 4
                bottom *= 4
                left *= 4

                # Draw box on original frame
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                cv2.putText(frame, name, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

                # If unknown → send alert
                current_time = time.time()
                if name == "Unknown":
                    if current_time - last_alert_time > ALERT_COOLDOWN:
                        print("⚠️ Intruder Detected!")
                        # Send SMS
                        # in body part you have to write your message
                        print(f"account_sid = {account_sid}")
                        print(f"auth_token = {auth_token}")
                        print(f"twilio_number = {twilio_number}")

                        message = client.messages.create(
                            body='Intruder Detected!!',
                            from_=twilio_number,
                            to=recipient_number)

                        #take pic of intruder
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        intruder_filename = f"intruder_{timestamp}.jpg"
                        cv2.imwrite(intruder_filename, frame)

                        email_subject = f"🚨 Security Alert: Intruder Detected - {timestamp}"
                        email_body = f"""
Security Alert!

An unrecognized person was detected at your door.

Detection Time: {timestamp}
Status: Entry Denied

Please find the attached photo of the intruder.

This is an automated message from your Smart Door Security System.
"""
                        send_email_alert(intruder_filename, email_subject, email_body)
                        last_alert_time = current_time
                        
                else:
                    if current_time - last_declare_time > DECLARE_COOLDOWN:
                        print(f"Owner:{name} Detected!")
                        # Send SMS
                        # in body part you have to write your message
                        print(f"account_sid = {account_sid}")
                        print(f"auth_token = {auth_token}")
                        print(f"twilio_number = {twilio_number}")
                        message = client.messages.create(
                            body='Intruder Detected!!Permission denied\n',
                            from_=twilio_number,
                            to=recipient_number
                        )
                        print(f"Message sent with SID: {message.sid}")
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        last_declare_time = current_time


                         # TODO: Send notification (email of pic)


    except Exception as e:
        print(f"Error in face processing: {e}")
        # Continue without crashing
        pass

    cv2.imshow("ESP32-CAM Security Feed", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()