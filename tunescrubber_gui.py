# TuneScrubber -- haptic feedback for audio files
# Some graph code borrwed from https://linuxtut.com/en/dc72976987d7ef485df1/


# Standard libraries
import logging
import threading
from time import sleep

# Third-party libraries
import PySimpleGUI as sg
import serial
import serial.tools.list_ports
from scipy.signal import hilbert
from scipy.io import wavfile
import numpy as np
from sklearn import preprocessing

GRAPH_SIZE = (400,300)
ANGLE_MAX = 3600
MAX_ENV_SAMPS = 1000

ser = serial.Serial()
ser.baudrate = 115200

torque = 0

ports_dropdown = sg.Combo((), readonly=True, size=(20, 5), key='Ports')
torque_slider = sg.Slider(range=(-360, 360), default_value=0, enable_events=True, orientation='horizontal', key='Torque')
graph = sg.Graph(canvas_size=GRAPH_SIZE, graph_bottom_left=(0,0), graph_top_right=GRAPH_SIZE, key='Graph')
open_port = sg.Text('')
file_browse = sg.FileBrowse(button_text='Open File', key='File', file_types = (('.wav files', '*.wav'),), enable_events=True) 

sg.change_look_and_feel('LightGreen')
def window_function():
    global envelope
    
    # sg.theme('DarkAmber')   # Add a touch of color
    # All the stuff inside your window.
    layout = [
        [sg.Text('Ports'), ports_dropdown, sg.Button('Refresh')],
        [sg.Button('Open Port'), open_port],
        [file_browse],
        [graph],
        [sg.Text('Torque'), torque_slider, sg.Button('Reset')],
        [sg.Button('Quit')],
    ]
    # Create the Window
    window = sg.Window('Serial Communicator', [layout], resizable=True, finalize=True)
    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == 'Quit': # if user closes window or clicks cancel
            break
        elif event == 'Open Port':
            port = values['Ports']
            ser.port = port
            if not ser.is_open:
                ser.open()
            open_port.update(f'Current port: {port}')
        elif event == 'File':
            sample_rate, audio_buffer = wavfile.read(values['File'])
            envelope = calc_envelope(audio_buffer)
            draw_buffer(envelope)
        elif event == 'Refresh':
            ports = serial.tools.list_ports.comports()
            ports_dropdown.update(values=[port for (port, desc, hwid) in ports])
        elif event == 'Torque':
            torque = values['Torque']
            if ser.is_open:
                ser.write(bytes(str(int(torque)), 'utf-8'))
        elif event == 'Reset':
            torque_slider.update(0)
            torque = 0
            if ser.is_open:
                ser.write(bytes(str(0), 'utf-8'))
            
    window.close()

# Calculates the amplitude envelope of the audio file
def calc_envelope(buffer):
    analytic_signal = hilbert(buffer)
    return preprocessing.normalize(np.abs(analytic_signal))

def draw_buffer(buffer):
    graph.erase()
    curX = 0
    curIdx = 0
    lastY = 0
    num_samps = min(MAX_ENV_SAMPS, len(envelope))
    xInterval = GRAPH_SIZE[0] / num_samps
    envInterval = len(envelope) / num_samps
    for i in range(num_samps):
        graph.DrawLine((curX, lastY), (curX + xInterval, envelope[int(curIdx)][0] * GRAPH_SIZE[1]))
        lastY = envelope[int(curIdx)][0] * GRAPH_SIZE[1]
        curX += xInterval
        curIdx += envInterval

def serial_read_thread():
    while True:
        if not ser.is_open:
            sleep(1)
            continue
        data = ser.read_until(expected=' '.encode('utf-8')).decode('utf-8', 'backslashreplace')
        print(data)
        try:
            angle = int(data)
        except ValueError:
            logging.warning(f'{data} is not an integer')
            continue

def main():
    w = threading.Thread(target=window_function)
    w.start()
    x = threading.Thread(target=serial_read_thread, daemon=True)
    x.start()


if __name__ == '__main__':
    main()