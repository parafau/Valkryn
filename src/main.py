import cv2
import face_recognition
import numpy as np
import smtplib
from email.mime.text import MIMEText

# ESP32-CAM stream URL
ESP32_STREAM_URL = "http:dummy"  # change to your IP

# Load known faces
known_face_encodings = []
known_face_names = []

# Example: add owner's photo
owner_img = face_recognition.load_image_file("Valkryn\ssets\shravan.jpg")
owner_enc = face_recognition.face_encodings(owner_img)[0]
known_face_encodings.append(owner_enc)
known_face_names.append("Owner")

# Start video stream
cap = cv2.VideoCapture(ESP32_STREAM_URL)

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to grab frame")
        break

    # Resize for speed
    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    rgb_small_frame = small_frame[:, :, ::-1]

    # Face detection
    face_locations = face_recognition.face_locations(rgb_small_frame)
    face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
        name = "Unknown"

        face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
        best_match = np.argmin(face_distances)
        if matches[best_match]:
            name = known_face_names[best_match]

        # Draw box
        top, right, bottom, left = [v * 4 for v in (top, right, bottom, left)]
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
        cv2.putText(frame, name, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        # If unknown → send alert
        if name == "Unknown":
            print("⚠️ Intruder Detected!")
            # Example: Save snapshot
            cv2.imwrite("intruder.jpg", frame)

            # TODO: Send notification (email/Telegram/Push)

    cv2.imshow("ESP32-CAM Security Feed", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
