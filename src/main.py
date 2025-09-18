import cv2
import face_recognition
import numpy as np
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import time

# ESP32-CAM stream URL
ESP32_STREAM_URL = "http:dummy"  # change to your IP

# Add error handling and alert cooldown
last_alert_time = 0
ALERT_COOLDOWN = 30  # seconds between alerts


# Load known faces
known_face_encodings = []
known_face_names = []

# Example: add owner's photo
try:
    owner_img = face_recognition.load_image_file(r"../assets/sample_img.jpg")
    owner_encodings = face_recognition.face_encodings(owner_img)
    if len(owner_encodings) > 0:
        known_face_encodings.append(owner_encodings[0])
        known_face_names.append("Owner")
    else:
        print("No face found in owner image!")
except FileNotFoundError:
    print("Owner image not found!")

# Start video stream
cap = cv2.VideoCapture(r"../assets/sample_vid.mp4")
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
        # print(f"Found {len(face_locations)} faces") commented
        
        if len(face_locations) > 0:
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
            # print(f"Generated {len(face_encodings)} encodings") commented
            
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
                if name == "Unknown":
                    current_time = time.time()
                    if current_time - last_alert_time > ALERT_COOLDOWN:
                        print("⚠️ Intruder Detected!")
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        cv2.imwrite(f"intruder_{timestamp}.jpg", frame)
                        last_alert_time = current_time
                         # TODO: Send notification (email/Telegram/Push)


    except Exception as e:
        print(f"Error in face processing: {e}")
        # Continue without crashing
        pass

    cv2.imshow("ESP32-CAM Security Feed", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()