import cv2
import face_recognition
import numpy as np
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import time
from twilio.rest import Client

# in this part you have to replace account_sid
# auth_token, twilio_number, recipient_number with your actual credential

account_sid = 'ACfa527913d395809445f3d8c2490d0b01'
auth_token = '79ac85f018fc003cbd554116d2abf554'
twilio_number = '+14482317830'
recipient_number = '+919930859426'

# Create Twilio client
client = Client(account_sid, auth_token)




# ESP32-CAM stream URL
ESP32_STREAM_URL = "https:"  # change to your IP

# Add error handling and alert cooldown
last_alert_time = 0
ALERT_COOLDOWN = 30  # seconds between alerts


# Load known faces
known_face_encodings = []
known_face_names = []

# Example: add owner's photo
try:

    owner_img = face_recognition.load_image_file(r"../assets/joel.jpg")
    owner_encodings = face_recognition.face_encodings(owner_img)
    if len(owner_encodings) > 0:
        known_face_encodings.append(owner_encodings[0])
        known_face_names.append("Joel")

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
                if name == "Unknown":
                    current_time = time.time()
                    if current_time - last_alert_time > ALERT_COOLDOWN:
                        print("⚠️ Intruder Detected!")
                        # # Send SMS
                        # # in body part you have to write your message
                        # message = client.messages.create(
                        #     body='Intruder Detected!!',
                        #     from_=twilio_number,
                        #     to=recipient_number
                        # )
                        # print(f"Message sent with SID: {message.sid}")

                        #take pic of intruder
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        cv2.imwrite(rf"intruder_{timestamp}.jpg", frame)
                        last_alert_time = current_time
                        

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