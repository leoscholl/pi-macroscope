import time
import picamera
import numpy as np
import os
import time
from pynput import mouse, keyboard

# Arguments
res_x = 1280
res_y = 720
cursor_size = 10 # pixels
min_roi_size = 100 # pixels
recording_dir = '/home/pi/recordings'
filename = 'video'
recording_duration = 10 # seconds

# Keyboard listener for escape
run = True
def on_press(key):
    global run
    if key == keyboard.Key.esc:
        run = False

# Mouse listener for coordinates and clicks
mouse_x = 0
mouse_y = 0
roi = np.zeros(4)
roi_changing = False
roi_changed = False
record_changed = False
recording = False
record_start_time = None
def on_move(x, y):
    global mouse_x, mouse_y
    mouse_x = x
    mouse_y = y

def on_click(x, y, button, pressed):
    global roi, roi_changing, roi_changed, record_mask, record_changed
    if record_mask[y,x] and pressed:
        record_changed = True
    elif pressed:
        roi[0] = x
        roi[1] = y
        roi_changing = True
    else:
        roi_changing = False
        roi_changed = True

exp = 0
def on_scroll(x, y, dx, dy):
    global camera, exp
    exp += dy
    if exp > 25:
        exp = 25
    if exp < -25:
        exp = -25
    camera.exposure_compensation = exp

# ROI update
def change_roi():
    if roi[2] < 0 and roi[3] < 0:
        roi[0] = roi[0] + roi[2]
        roi[1] = roi[1] + roi[3]
        roi[2] = -roi[2]
        roi[3] = -roi[3]
    if roi[2] < min_roi_size or roi[3] < min_roi_size:
        camera.zoom = (0.0, 0.0, 1.0, 1.0)
    else:
        camera.zoom = (roi[0]/res_x, roi[1]/res_y, roi[2]/res_x, roi[3]/res_y)

def create_circular_mask(h, w, center=None, radius=None):

    if center is None: # use the middle of the image
        center = (int(w/2), int(h/2))
    if radius is None: # use the smallest distance between the center and image walls
        radius = min(center[0], center[1], w-center[0], h-center[1])

    Y, X = np.ogrid[:h, :w]
    dist_from_center = np.sqrt((X - center[0])**2 + (Y-center[1])**2)

    mask = dist_from_center <= radius
    return mask

# Ask for filename
value = input('Session name? (default is "%s") ' % filename)
if value:
    filename = value
i = 0

camera = picamera.PiCamera()
camera.resolution = (res_x, res_y)
camera.framerate = 24
camera.start_preview()

# Start listeners
l_mouse = mouse.Listener(
    on_move=on_move,
    on_click=on_click,
    on_scroll=on_scroll)
l_mouse.start()
l_keyboard = keyboard.Listener(
    on_press=on_press)
l_keyboard.start()

# Create overlays
a = np.zeros((res_y, res_x, 4), dtype=np.uint8)
o_mouse = camera.add_overlay(a.tobytes(), layer=4)
o_roi = camera.add_overlay(a.tobytes(), layer=0)
record_mask = create_circular_mask(res_y, res_x, (30, 30), 10)
a[record_mask,0] = 0xff
a[record_mask,3] = 0x40
o_record = camera.add_overlay(a.tobytes(), layer=3)

# Main loop
while run:
    
    # Draw the mouse
    a = np.zeros((res_y, res_x, 4), dtype=np.uint8)
    a[mouse_y, int(mouse_x-cursor_size/2):int(mouse_x+cursor_size/2), :] = 0xff
    a[int(mouse_y-cursor_size/2):int(mouse_y+cursor_size/2), mouse_x, :] = 0xff
    o_mouse.update(a.tobytes())
    
    # Handle recording start/stop
    if record_changed:
        recording = not recording
        a = np.zeros((res_y, res_x, 4), dtype=np.uint8)
        a[record_mask,0] = 0xff
        if recording:
            a[record_mask,3] = 0xff
            while os.path.exists(os.path.join(recording_dir, "%s%03d.h264" % (filename,i))):
                i += 1
            camera.start_recording(os.path.join(recording_dir, "%s%03d.h264" % (filename,i)))
            record_start_time = time.time()
        else:
            a[record_mask,3] = 0x40
            camera.stop_recording()
        o_record.update(a.tobytes())
        record_changed = False
    
    # Split the recording up
    if recording and time.time() - record_start_time > recording_duration:
        i += 1
        camera.split_recording(os.path.join(recording_dir, "%s%03d.h264" % (filename,i)))
        record_start_time = time.time()
        
    # Handle ROI selection
    if roi_changing:
        roi[2] = mouse_x - roi[0]
        roi[3] = mouse_y - roi[1]
        x_y = roi[2]*res_y/res_x
        y_x = roi[3]*res_x/res_y
        if roi[2] > y_x:
            roi[2] = y_x
        else:
            roi[3] = x_y
        a = np.zeros((res_y, res_x, 4), dtype=np.uint8)
        a[int(roi[1]):int(roi[1]+roi[3]), int(roi[0]):int(roi[0]+roi[2]), 0] = 0xff
        a[int(roi[1]):int(roi[1]+roi[3]), int(roi[0]):int(roi[0]+roi[2]), 3] = 0x40
        o_roi.update(a.tobytes())
        o_roi.layer = 5
    elif roi_changed:
        o_roi.layer = 0
        change_roi()