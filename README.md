# Valkryn
A security camera system with sms/gmail alerting using facial recognition with OpenCV

the system recieves a live video feed from esp32 cam module and detects and recognizes the face in the live video with the given owner face images. On recognizing a "non-owner" face the program sends an sms alert to the owner's number and mails the photo of the intruder detected to owner.

## Pre-requisites
* Install "Visual Studio Code" 
* Install "Visual Studio" to install the extension "Desktop Development with C++" (if you don't already have it)

* Install Cmake (Select the "Add to Path" checkbox)

## Setup
* Open your Terminal and go to the directory where you want the repository 

(Optional:
* Create a python virtual environment)

* Clone the repo in the same directory using
`git clone https://github.com/parafau/Valkryn.git`

* Install all required python libraries using
`pip install -r "requirements.txt" `

* Upload the picture of the owner or the face to be recognized in "assets" and give path for the same in src/main.py

* Give the location of the video source(Give the path as the URL of the video stream incase using esp32 CAM module)

* Run the src/main.py


