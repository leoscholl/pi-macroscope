import time
import picamera
import numpy as np
import os
import copy
from pynput import mouse, keyboard
from threading import Timer
import sys, select
import subprocess

def create_circular_mask(h, w, center=None, radius=None):

    if center is None: # use the middle of the image
        center = (int(w/2), int(h/2))
    if radius is None: # use the smallest distance between the center and image walls
        radius = min(center[0], center[1], w-center[0], h-center[1])

    Y, X = np.ogrid[:h, :w]
    dist_from_center = np.sqrt((X - center[0])**2 + (Y-center[1])**2)

    mask = dist_from_center <= radius
    return mask

def timeout_input(prompt, timeout=3, default=""):
    print(prompt, end=': ', flush=True)
    inputs, outputs, errors = select.select([sys.stdin], [], [], timeout)
    print()
    return (0, sys.stdin.readline().strip()) if inputs else (-1, default)

class Macroscope:

    def __init__(self, recording_path, recording_session, cursor_size=12, min_roi_size=100, recording_duration=600):
        
        # Constants
        self.recording_path = recording_path
        self.recording_session = recording_session
        self.cursor_size = cursor_size # in pixels
        self.min_roi_size = min_roi_size # in pixels
        self.recording_duration = recording_duration # in seconds

        # Variables
        self.preview = False
        self.recording = False
        self.recording_number = 0
        self.roi = np.zeros(4)
        self.roi_changing = False
        self.mouse_pos = (0, 0)
        self.update = False
        self.exp = 0

    # Pynput mouse listeners
    def on_mouse_move(self, x, y):
        if not self.preview:
            return
        if x < 0: x = 0
        if x >= self.resolution[0]: x = self.resolution[0] - 1
        if y < 0: y = 0
        if y >= self.resolution[1]: y = self.resolution[1] - 1
        self.mouse_pos = (x, y)
        self.update = True
        if self.roi_changing:
            roi = self.roi
            roi[2] = x - roi[0]
            roi[3] = y - roi[1]
            x_y = roi[2]*self.resolution[1]/self.resolution[0]
            y_x = roi[3]*self.resolution[0]/self.resolution[1]
            if roi[2] > y_x:
                roi[2] = y_x
            elif roi[2] < -y_x:
                roi[2] = -y_x
            elif roi[3] > x_y:
                roi[3] = x_y
            else:
                roi[3] = -x_y

    def on_mouse_click(self, x, y, button, pressed):
        if not self.preview:
            return
        if self.record_mask[y,x] and pressed:
            recording = not self.recording
            if recording:
                while os.path.exists(self.get_recording_filename()):
                    self.recording_number += 1
                self.camera.start_recording(self.get_recording_filename(), splitter_port=2)
                print('Started recording %s ' % self.get_recording_filename())
                self.recording_start_time = time.time()
            else:
                self.camera.stop_recording(splitter_port=2)
                print('Stopped recording.')
            self.recording = recording
            self.update = True
        elif self.record_mask[y,x]:
            pass
        elif pressed:
            self.roi[0] = x
            self.roi[1] = y
            self.roi[2] = 0
            self.roi[3] = 0
            self.roi_changing = True
            self.o_roi.layer = 5
        else:
            self.roi_changing = False
            self.o_roi.layer = 0
            self.change_roi()
            self.roi = np.zeros(4)

    def on_mouse_scroll(self, x, y, dx, dy):
        if not self.preview:
            return
        if dy > 0 and self.camera.exposure_compensation < 25:
            self.camera.exposure_compensation += 1
        elif dy < 0 and self.camera.exposure_compensation > -25:
            self.camera.exposure_compensation -= 1

    def on_keypress(self, key):
        if key == keyboard.Key.esc:
            return False
        elif hasattr(key, 'char') and key.char == "p":
            if self.preview:
                self.camera.stop_preview()
                self.o_roi.layer = 0
                self.o_record.layer = 0
                self.o_mouse.layer = 0
                self.preview = False
            else:
                self.camera.start_preview()
                self.o_roi.layer = 0
                self.o_record.layer = 3
                self.o_mouse.layer = 4
                self.preview = True

    def draw_overlays(self):

        # Mouse
        a = np.zeros((self.resolution[1], self.resolution[0], 4), dtype=np.uint8)
        x, y = self.mouse_pos
        a[y, int(x-self.cursor_size/2):int(x+self.cursor_size/2), :] = 0xff
        a[int(y-self.cursor_size/2):int(y+self.cursor_size/2), x, :] = 0xff
        self.o_mouse.update(a.tobytes())

        # ROI
        if self.roi_changing:
            a = np.zeros((self.resolution[1], self.resolution[0], 4), dtype=np.uint8)
            roi = copy.deepcopy(self.roi)
            if roi[2] < 0:
                roi[0] = roi[0] + roi[2]
                roi[2] = -roi[2]
            if roi[3] < 0:
                roi[1] = roi[1] + roi[3]
                roi[3] = -roi[3]
            a[int(roi[1]):int(roi[1]+roi[3]), int(roi[0]):int(roi[0]+roi[2]), :] = 0xff
            a[int(roi[1]):int(roi[1]+roi[3]), int(roi[0]):int(roi[0]+roi[2]), 3] = 0x10
            self.o_roi.update(a.tobytes())
        
        # Recording
        a = np.zeros((self.resolution[1], self.resolution[0], 4), dtype=np.uint8)
        a[self.record_mask,0] = 0xff
        if self.recording:
            a[self.record_mask,3] = 0xff
        else:
            a[self.record_mask,3] = 0x40
        self.o_record.update(a.tobytes())


    # ROI update
    def change_roi(self):
        roi = self.roi
        if roi[2] < 0:
            roi[0] = roi[0] + roi[2]
            roi[2] = -roi[2]
        if roi[3] < 0:
            roi[1] = roi[1] + roi[3]
            roi[3] = -roi[3]
        if roi[2] < self.min_roi_size or roi[3] < self.min_roi_size:
            self.camera.zoom = (0.0, 0.0, 1.0, 1.0)
            roi = [0, 0, self.resolution[0], self.resolution[1]]
        else:
            self.camera.zoom = (roi[0]/self.resolution[0], roi[1]/self.resolution[1], 
                roi[2]/self.resolution[0], roi[3]/self.resolution[1])

    # Main loop
    def run(self, stream=False):

        # Init camera
        camera = picamera.PiCamera()
        camera.framerate = 30
        self.camera = camera
        self.resolution = camera.resolution

        # Add overlays
        a = np.zeros((self.resolution[1], self.resolution[0], 4), dtype=np.uint8)
        self.o_mouse = camera.add_overlay(a.tobytes(), layer=0)
        self.o_roi = camera.add_overlay(a.tobytes(), layer=0)
        record_mask = create_circular_mask(self.resolution[1], self.resolution[0], (25, 25), 11)
        a[record_mask,0] = 0xff
        a[record_mask,3] = 0x40
        self.o_record = camera.add_overlay(a.tobytes(), layer=3)
        self.record_mask = record_mask
        
        # Listen to mouse and keyboard events
        l_mouse = mouse.Listener(
            on_move=lambda x,y: self.on_mouse_move(x,y),
            on_click=lambda x,y,button,pressed: self.on_mouse_click(x,y,button,pressed),
            on_scroll=lambda x,y,dx,dy: self.on_mouse_scroll(x,y,dx,dy))
        l_mouse.start()
        l_keyboard = keyboard.Listener(on_press=lambda key: self.on_keypress(key))
        l_keyboard.start()
        
        # Start streaming or start the preview
        if stream:
            vlc = subprocess.Popen([
                'cvlc', 'stream:///dev/stdin',
                #'--sout', '#rtp{sdp=rtsp://:8555/',
                ':demux=h264',
                ], stdin=subprocess.PIPE)
            camera.start_recording(vlc.stdin, format='h264', quality=20, resize=(640, 480))
        else:
            self.on_keypress(keyboard.KeyCode.from_char('p'))
            
        # Loop until escape key is pressed
        while l_keyboard.running: 

            if self.update:
                self.draw_overlays()
                self.update = False
                time.sleep(1/100) # try not to update the overlays super fast
                
            # Split the recording up if necessary
            if self.recording and time.time() - self.recording_start_time > self.recording_duration:
                self.recording_number += 1
                self.camera.split_recording(self.get_recording_filename(), splitter_port=2)
                self.recording_start_time = time.time()
                print('... %s ' % self.get_recording_filename())
            
        
        # Cleanup
        self.camera.remove_overlay(self.o_mouse)
        self.camera.remove_overlay(self.o_roi)
        self.camera.remove_overlay(self.o_record)
        if self.recording:
            self.camera.stop_recording(splitter_port=2)
        l_mouse.stop()
        if stream:
            self.camera.stop_recording()
            vlc.kill()

# Path helper
    def get_recording_filename(self):
        return os.path.join(self.recording_path, "%s%03d.h264" % (self.recording_session,self.recording_number))


if __name__ == "__main__":
    recording_dir = '/home/pi/recordings'
    filename = 'video'

    # Ask for filename
    prompt = 'Session name? (default is "%s") ' % filename
    ans, value = timeout_input(prompt, timeout=10, default=filename)
    if ans == -1 or value == "":
        print('Using default...')
    else:
        filename = value
    
    print('Press "p" to start/stop preview')
    print('Press "Esc" to exit')
    
    try:
        scope = Macroscope(recording_dir, filename)
        scope.run()
    except Exception as e:
        print(e)
        timeout_input("Press any key to exit", timeout=60)
        
