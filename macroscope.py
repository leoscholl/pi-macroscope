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
        self.image_number = 0
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
            self.toggle_recording()
        elif self.record_mask[y,x]:
            pass
        elif pressed:
            self.roi[0] = x
            self.roi[1] = y
            self.roi[2] = 0
            self.roi[3] = 0
            self.roi_changing = True
        else:
            self.roi_changing = False
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
        elif hasattr(key, 'char') and key.char == "p": # preview
            if self.preview:
                self.camera.stop_preview()
                self.camera.remove_overlay(self.overlay)
                self.preview = False
            else:
                a = np.zeros((self.resolution[1], self.resolution[0], 4), dtype=np.uint8)
                self.overlay = self.camera.add_overlay(a.tobytes(), layer=3)
                self.camera.start_preview()
                self.preview = True
        elif key == keyboard.Key.space: # recording
            self.toggle_recording()
        elif key == keyboard.Key.enter:
            self.take_still()
        elif hasattr(key, 'char') and key.char == "r": # rotate
            self.camera.rotation = self.camera.rotation + 90

    def draw_overlay(self):
        a = np.zeros((self.resolution[1], self.resolution[0], 4), dtype=np.uint8)
        
        # Recording
        a[self.record_mask,0] = 0xff
        if self.recording:
            a[self.record_mask,3] = 0xff
        else:
            a[self.record_mask,3] = 0x40

        # ROI
        if self.roi_changing:
            roi = copy.deepcopy(self.roi)
            if roi[2] < 0:
                roi[0] = roi[0] + roi[2]
                roi[2] = -roi[2]
            if roi[3] < 0:
                roi[1] = roi[1] + roi[3]
                roi[3] = -roi[3]
            a[int(roi[1]):int(roi[1]+roi[3]), int(roi[0]):int(roi[0]+roi[2]), :] = 0xff
            a[int(roi[1]):int(roi[1]+roi[3]), int(roi[0]):int(roi[0]+roi[2]), 3] = 0x10
        
        # Mouse
        x, y = self.mouse_pos
        a[y, int(x-self.cursor_size/2):int(x+self.cursor_size/2), :] = 0xff
        a[int(y-self.cursor_size/2):int(y+self.cursor_size/2), x, :] = 0xff
        self.overlay.update(a.tobytes())


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
            
    def toggle_recording(self):
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
        
    def take_still(self):
        filename = os.path.join(self.recording_path, "%s-still%03d.jpg" % (self.recording_session, self.image_number))
        while os.path.exists(filename):
            self.image_number += 1
            filename = os.path.join(self.recording_path, "%s-still%03d.jpg" % (self.recording_session, self.image_number))
        self.camera.capture(filename)
        print("Captured image %s" % filename)

    # Main loop
    def run(self, stream=False):

        # Init camera
        camera = picamera.PiCamera()
        camera.framerate = 30
        self.camera = camera
        self.resolution = camera.resolution
        self.record_mask = create_circular_mask(self.resolution[1], self.resolution[0], (25, 25), 11)
        
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
                self.draw_overlay()
                self.update = False
                time.sleep(1/60) # try not to update the overlays super fast
                
            # Split the recording up if necessary
            if self.recording and time.time() - self.recording_start_time > self.recording_duration:
                self.recording_number += 1
                self.camera.split_recording(self.get_recording_filename(), splitter_port=2)
                self.recording_start_time = time.time()
                print('... %s ' % self.get_recording_filename())
            
        
        # Cleanup
        if self.preview:
            self.camera.remove_overlay(self.overlay)
        if self.recording:
            self.camera.stop_recording(splitter_port=2)
        l_mouse.stop()
        if stream:
            self.camera.stop_recording()
            vlc.kill()
        self.camera.close()

# Path helper
    def get_recording_filename(self):
        return os.path.join(self.recording_path, "%s%03d.h264" % (self.recording_session,self.recording_number))


if __name__ == "__main__":
    recording_dir = '/home/pi/recordings'
    filename = 'macroscope'

    # Ask for filename
    prompt = 'Session name? (default is "%s") ' % filename
    ans, value = timeout_input(prompt, timeout=30, default=filename)
    if ans == -1 or value == "":
        print('Using default...')
    else:
        filename = valuep
    
    print('--------------------------------------------------')
    print('Press "P" to start/stop preview')
    print('Press Space to start/stop recording')
    print('Press Enter to take a still image')
    print('Press "R" to rotate camera')
    print('Use scroll wheel to adjust brightness')
    print('Click and drag to set ROI. Click anywhere to reset')
    print('Press "Esc" to exit')
    print('--------------------------------------------------')
    print('')
    time.sleep(1)
    
    try:
        scope = Macroscope(recording_dir, filename)
        scope.run()
    except Exception as e:
        print(e)
        timeout_input("Press any key to exit", timeout=60)
        
