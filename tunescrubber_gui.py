# TuneScrubber -- haptic feedback for audio files
# Some graph code borrwed from https://linuxtut.com/en/dc72976987d7ef485df1/


# Standard libraries
from collections import deque
from time import sleep
import atexit
import logging
import threading
import wave

# Third-party libraries
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.pyplot import figure, show 
from scipy.io import wavfile
from scipy.signal import hilbert
from sklearn import preprocessing
import PySimpleGUI as sg
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.pyplot as plt
import numpy as np
import simpleaudio as sa
import serial
import serial.tools.list_ports

matplotlib.use('TkAgg')

GRAPH_SIZE = (400,300)
ANGLE_MAX = 3600
MAX_ENV_SAMPS = 1000

ser = serial.Serial()
ser.baudrate = 115200

playback_buffer = deque()
sample_rate = audio_buffer = num_channels = bytes_per_sample = None
playhead_position = 0
seconds_per_rotation = 1



ports_dropdown = sg.Combo((), readonly=True, size=(20, 5), key='Ports')
zoom_slider = sg.Slider(range=(1, 3), default_value=seconds_per_rotation, enable_events=True, orientation='horizontal', key='Zoom')
canvas = sg.Canvas(key='Canvas')
open_port = sg.Text('')
file_browse = sg.FileBrowse(button_text='Open File', key='File', file_types = (('.wav files', '*.wav'),), enable_events=True) 
position_indicator = sg.ProgressBar(max_value=3600, orientation='horizontal', key='position_indicator')

sg.change_look_and_feel('LightGreen')
def window_function():
    global envelope, sample_rate, audio_buffer, num_channels, bytes_per_sample
    global seconds_per_rotation
    
    # sg.theme('DarkAmber')   # Add a touch of color
    # All the stuff inside your window.
    layout = [
        [sg.Text('Ports'), ports_dropdown, sg.Button('Refresh')],
        [sg.Button('Open Port'), open_port],
        [file_browse],
        [canvas],
        [position_indicator],
        [sg.Text('Zoom'), zoom_slider, sg.Button('Reset')],
        [sg.Button('Quit')],
    ]
    # Create the Window
    window = sg.Window('TuneScrubber', [layout], resizable=True, finalize=True)

    plt.figure(1)
    plt.subplot(111)
    fig = matplotlib.figure.Figure(figsize=(5, 4), dpi=100)
    envPlot = fig.add_subplot(111)
    fig_canvas_agg = FigureCanvasTkAgg(fig, canvas.TKCanvas)
    fig_canvas_agg = draw_figure(fig_canvas_agg)

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
            filepath = values['File']
            with wave.Wave_read(filepath) as w:
                bytes_per_sample = w.getsampwidth()
                num_channels = w.getnchannels()
            sample_rate, audio_buffer = wavfile.read(filepath)
            envelope = calc_envelope(audio_buffer)
            plt.clf()
            envPlot.plot(envelope)
            fig_canvas_agg = draw_figure(fig_canvas_agg)
        elif event == 'Refresh':
            ports = serial.tools.list_ports.comports()
            ports_dropdown.update(values=[port for (port, desc, hwid) in ports])
        elif event == 'Zoom':
            seconds_per_rotation = values['Zoom']

            
    window.close()


# Calculates the amplitude envelope of the audio file
def calc_envelope(buffer):
    if type(buffer[0]) == list:
        analytic_signal = np.abs(hilbert(buffer)[:, 0])
    else:
        analytic_signal = np.abs(hilbert(buffer))
    return analytic_signal / np.linalg.norm(analytic_signal)

def draw_figure(figure_canvas_agg):
    figure_canvas_agg.draw()
    figure_canvas_agg.get_tk_widget().pack(side='top', fill='both', expand=1)
    return figure_canvas_agg

def serial_read_thread():
    global playhead_position, playback_buffer
    angle = last_angle = None
    while True:
        if not ser.is_open:
            sleep(1)
            continue
        data = ser.read_until(expected=' '.encode('utf-8')).decode('utf-8', 'backslashreplace')
        try:
            angle = int(data)
        except ValueError:
            logging.warning(f'{data} is not an integer')
            continue
        if last_angle is None:
            last_angle = angle
            continue
        # Angle goes from Quadrant 4 to Quadrant 1
        if angle < ANGLE_MAX // 4 and last_angle > (ANGLE_MAX // 4)*3:
            last_angle -= ANGLE_MAX
        # Angle goes from Quadrant 1 to Quadrant 4
        if angle > (ANGLE_MAX // 4)*3 and last_angle < ANGLE_MAX // 4:
            last_angle += ANGLE_MAX
        position_indicator.update(angle)
        delta = last_angle - angle
        last_angle = angle
        if abs(delta) < 10:
            continue
        if delta >= 0:
            step = 1
        else:
            step = -1
        samples_per_delta_unit = int((sample_rate / ANGLE_MAX) * seconds_per_rotation)
        new_playhead_position = max(playhead_position + (delta*samples_per_delta_unit), 0)
        if new_playhead_position == 0:
            continue
        chunk = audio_buffer[playhead_position:new_playhead_position:step].copy(order='C')
        playback_buffer.appendleft(chunk)
        playhead_position = new_playhead_position
        print(f'new playhead: {new_playhead_position}')

def playback_thread():
    global playback_buffer
    local_buffer = None
    while True:
        sleep(0.01)
        while playback_buffer:
            chunk = playback_buffer.pop()
            if local_buffer is None:
                local_buffer = chunk
            else:
                local_buffer = np.concatenate((local_buffer, chunk))
        if local_buffer is not None:
            print(f'playing buffer of size {len(local_buffer)}')
            sa.play_buffer(local_buffer, num_channels, bytes_per_sample, sample_rate)
            local_buffer = None



def reset_torque():
    ser.write(bytes('0', 'utf-8'))


def main():
    atexit.register(reset_torque)
    threading.Thread(target=window_function).start()
    threading.Thread(target=serial_read_thread, daemon=True).start()
    threading.Thread(target=playback_thread, daemon=True).start()


if __name__ == '__main__':
    main()