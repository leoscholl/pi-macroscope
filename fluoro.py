from picamera import PiCamera
from time import sleep
from fractions import Fraction
import os

recording_path = '/home/pi/Videos'
recording_session = 'test_01'
n_img = 2

# Force sensor mode 3 (the long exposure mode), set
# the framerate to 1/6fps, the shutter speed to 6s,
# and ISO to 800 (for maximum gain)
camera = PiCamera(
    resolution=(1280, 1024),
    framerate=Fraction(1, 10),
    sensor_mode=3)
camera.shutter_speed = 10000000
camera.iso = 25
# Give the camera a good long time to set gains and
# measure AWB (you may wish to use fixed AWB instead)
sleep(30)
camera.exposure_mode = 'off'
# Finally, capture an image with a 6s exposure. Due
# to mode switching on the still port, this will take
# longer than 6 seconds
image_number = 0
filename = os.path.join(recording_path, "%s-fluoro-1280x1024-RGB%03d.png" % (recording_session, image_number))
while os.path.exists(filename):
    image_number += 1
    filename = os.path.join(recording_path, "%s-fluoro-1280x1024-RGB%03d.png" % (recording_session, image_number))
camera.capture(filename)
print("Captured test image...")

# Capture a sequence of raw images
image_number = 0
filename = os.path.join(recording_path, "%s-fluoro-1280x1024-RGB%03d.raw" % (recording_session, image_number))
while os.path.exists(filename):
    image_number += 1
    filename = os.path.join(recording_path, "%s-fluoro-1280x1024-RGB%03d.raw" % (recording_session, image_number))

filenames = [
    os.path.join(recording_path, "%s-fluoro-1280x1024-RGB%03d.raw" % (recording_session, idx))
    for idx in range(image_number, image_number + n_img)
]
camera.capture_sequence(filenames, format='rgb')
print(f"Captured {n_img} images")


