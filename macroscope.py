import time
import picamera
import numpy as np
import os
import time
from pynput import mouse, keyboard
from threading import Timer

def create_circular_mask(h, w, center=None, radius=None):

    if center is None: # use the middle of the image
        center = (int(w/2), int(h/2))
    if radius is None: # use the smallest distance between the center and image walls
        radius = min(center[0], center[1], w-center[0], h-center[1])

    Y, X = np.ogrid[:h, :w]
    dist_from_center = np.sqrt((X - center[0])**2 + (Y-center[1])**2)

    mask = dist_from_center <= radius
    return mask

class Macroscope:

    def __init__(self, resolution, recording_path, recording_session, cursor_size=11, min_roi_size=100, recording_duration=600):
        
        # Constants
        self.resolution = resolution
        self.recording_path = recording_path
        self.recording_session = recording_session
        self.cursor_size = cursor_size # in pixels
        self.min_roi_size = min_roi_size # in pixels
        self.recording_duration = recording_duration # in seconds

        # Variables
        self.recording = False
        self.recording_number = 0
        self.roi = np.zeros(4)
        self.roi_changing = False
        self.exp = 0

    # Pynput mouse listeners
    def on_mouse_move(self, x, y):
        a = np.zeros((self.resolution[1], self.resolution[0], 4), dtype=np.uint8)
        a[y, int(x-self.cursor_size/2):int(x+self.cursor_size/2), :] = 0xff
        a[int(y-self.cursor_size/2):int(y+self.cursor_size/2), x, :] = 0xff
        self.o_mouse.update(a.tobytes())
        if self.roi_changing:
            roi = self.roi
            roi[2:3] = [x - roi[0], y - roi[1]]
            x_y = roi[2]*self.resolution[1]/self.resolution[0]
            y_x = roi[3]*self.resolution[0]/self.resolution[1]
            if roi[2] > y_x:
                roi[2] = y_x
            else:
                roi[3] = x_y
            a = np.zeros((self.resolution[1], self.resolution[0], 4), dtype=np.uint8)
            a[int(roi[1]):int(roi[1]+roi[3]), int(roi[0]):int(roi[0]+roi[2]), 0] = 0xff
            a[int(roi[1]):int(roi[1]+roi[3]), int(roi[0]):int(roi[0]+roi[2]), 3] = 0x40
            self.o_roi.update(a.tobytes())
            self.o_roi.layer = 5
            self.roi = roi

    def on_mouse_click(self, x, y, button, pressed):
        if self.record_mask[y,x] and pressed:
            self.recording = not self.recording
            a = np.zeros((self.resolution[1], self.resolution[0], 4), dtype=np.uint8)
            a[self.record_mask,0] = 0xff
            if self.recording:
                a[self.record_mask,3] = 0xff
                while os.path.exists(self.get_recording_filename()):
                    self.recording_number += 1
                self.camera.start_recording(self.get_recording_filename())
                self.record_start_time = time.time()
            else:
                a[self.record_mask,3] = 0x40
                self.camera.stop_recording()
            self.o_record.update(a.tobytes())
        elif pressed:
            self.roi[0:1] = [x, y]
            self.roi_changing = True
        else:
            self.roi_changing = False
            self.o_roi.layer = 0
            self.change_roi()         

    def on_mouse_scroll(self, x, y, dx, dy):
        self.exp += dy
        if self.exp > 25:
            self.exp = 25
        if self.exp < -25:
            self.exp = -25
        self.camera.exposure_compensation = self.exp

    # ROI update
    def change_roi(self):
        roi = self.roi
        if roi[2] < 0 and roi[3] < 0:
            roi[0] = roi[0] + roi[2]
            roi[1] = roi[1] + roi[3]
            roi[2] = -roi[2]
            roi[3] = -roi[3]
        if roi[2] < self.min_roi_size or roi[3] < self.min_roi_size:
            self.camera.zoom = (0.0, 0.0, 1.0, 1.0)
        else:
            self.camera.zoom = (roi[0]/self.resolution[0], roi[1]/self.resolution[1], 
                roi[2]/self.resolution[0], roi[3]/self.resolution[1])
            print("Changing sensor mode from %d" % self.camera.sensor_mode)
            if roi[2] < 1012 and roi[3] < 760:
                self.camera.sensor_mode = 4
            else:
                self.camera.sensor_mode = 2
            print("... to %d" % self.camera.sensor_mode)

    # Main loop
    def run(self):

        # Init camera
        camera = picamera.PiCamera()
        camera.resolution = tuple(self.resolution)
        camera.framerate = 30
        camera.start_preview()
        self.camera = camera

        # Add overlays
        a = np.zeros((self.resolution[1], self.resolution[0], 4), dtype=np.uint8)
        self.o_mouse = camera.add_overlay(a.tobytes(), layer=4)
        self.o_roi = camera.add_overlay(a.tobytes(), layer=0)
        record_mask = create_circular_mask(self.resolution[1], self.resolution[0], (30, 30), 10)
        a[record_mask,0] = 0xff
        a[record_mask,3] = 0x40
        self.o_record = camera.add_overlay(a.tobytes(), layer=3)
        self.record_mask = record_mask

        l_mouse = mouse.Listener(
            on_move=lambda x,y: self.on_mouse_move(x,y),
            on_click=lambda x,y,button,pressed: self.on_mouse_click(x,y,button,pressed),
            on_scroll=lambda x,y,dx,dy: self.on_mouse_scroll(x,y,dx,dy))
        l_mouse.start()

        def check_escape(key):
            if key == keyboard.Key.esc:
                return False
        l_keyboard = keyboard.Listener(on_press=check_escape)
        l_keyboard.start()

        while l_keyboard: # loop until escape key is pressed

            # Split the recording up if necessary
            if self.recording and time.time() - self.record_start_time > self.recording_duration:
                self.recording_number += 1
                self.camera.split_recording(self.get_recording_filename())
                self.record_start_time = time.time()       

    # Path helper
    def get_recording_filename(self):
        return os.path.join(self.recording_path, "%s%03d.h264" % (self.recording_session,self.recording_number))


if __name__ == "__main__":
    res_x = 1024
    res_y = 768
    recording_dir = '/home/pi/recordings'
    filename = 'video'

    # Ask for filename
    timeout = 5
    t = Timer(timeout, print, ['Using default...'])
    t.start()
    prompt = 'Session name? (default is "%s") ' % filename
    value = input(prompt)
    t.cancel()
    if value:
        filename = value

    scope = Macroscope([res_x, res_y], recording_dir, filename)
    scope.run()
    