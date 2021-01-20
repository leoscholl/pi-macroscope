# pi-macroscope
Simple GUI for pi camera that allows you to select an ROI for recording. Uses the picamera python library 

<img src="https://github.com/leoscholl/pi-macroscope/blob/main/hq-camera-mount.jpg" alt="Image of camera mount" width="250">

## Install
Download or clone this repo onto a raspberry pi

As of November 2020 you also need to manually update the picamera python module for compatability with the new HQ camera. See [leoscholl/picamera](https://github.com/leoscholl/picamera)

## Copy the shortcut
In the file manager, under Edit/Preferences/General, check the box for "Don't ask options on launch executable file". \
Drag `macroscope.desktop` to the desktop while holding <kbd>ctrl</kbd><kbd>alt</kbd> to make a copy.

## Use
You will need a mouse and keyboard if you want to make recordings and set the ROI. Make a copy of the shortcut into `/etc/xdg/autostart/` if you want it to start automatically.
* Create a "recordings" folder in your home directory.
* Double click the shortcut. Enter a session name for the recordings.
* Click and drag the mouse to set the ROI. Click anywhere to reset to the full frame.
* Scroll up or down to increase or decrease exposure compensation. One scroll is 1/6 of a stop.
* Press <kbd>P</kbd> to show/hide the preview.
* Press <kbd>R</kbd> to rotate the image by 90 degrees.
* Click the red circle at the top left or press <kbd>Space</kbd> to begin recording. The resolution of the recordings is currently defined by the resolution of the screen. What you see is what you get, minus the GUI overlays.
* Press <kbd>Enter</kbd> to take a still image.
* Press <kbd>Esc</kbd> to exit. This will stop recording if it is on. 
