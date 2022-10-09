# TuneScrubber -- haptic feedback for audio files
# Some graph code borrwed from https://linuxtut.com/en/dc72976987d7ef485df1/


# Standard libraries
import atexit
from time import sleep
import logging
import threading
import wave

# Third-party libraries
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.pyplot import figure, show 
from scipy.io import wavfile
from scipy.signal import hilbert
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

sample_rate = audio_buffer = num_channels = bytes_per_sample = None

torque = 0

ports_dropdown = sg.Combo((), readonly=True, size=(20, 5), key='Ports')
zoom_slider = sg.Slider(range=(0, 100), default_value=0, enable_events=True, orientation='horizontal', key='Torque')
canvas = sg.Canvas(key='Canvas')
open_port = sg.Text('')
file_browse = sg.FileBrowse(button_text='Open File', key='File', file_types = (('.wav files', '*.wav'),), enable_events=True) 
position_indicator = sg.ProgressBar(max_value=3600, orientation='horizontal', key='position_indicator')

sg.change_look_and_feel('LightGreen')
def window_function():
    global envelope, sample_rate, audio_buffer, num_channels, bytes_per_sample
    
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
            
    window.close()


def slice_buffer(buffer, begin, end):
    if begin <= end:
        step = 1
    else:
        step = -1
    return buffer[begin:end:step]

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
    absolute_position = last_absolute_position = 0
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
        inverse_torque = delta / 10
        # ser.write(bytes(str(inverse_torque), 'utf-8'))
        last_absolute_position = absolute_position
        absolute_position = max(0, absolute_position+delta)
        last_angle = angle
        print(f'last: {last_absolute_position} current: {absolute_position}')
        if last_absolute_position != absolute_position:
            chunk = slice_buffer(audio_buffer, last_absolute_position, absolute_position)
            chunk = chunk.copy(order='C') # See https://stackoverflow.com/questions/26778079/valueerror-ndarray-is-not-c-contiguous-in-cython for why this is needed.
            sa.play_buffer(chunk, num_channels=num_channels, bytes_per_sample=bytes_per_sample, sample_rate=sample_rate)

def reset_torque():
    ser.write(bytes('0', 'utf-8'))


def main():
    atexit.register(reset_torque)
    w = threading.Thread(target=window_function)
    w.start()
    x = threading.Thread(target=serial_read_thread, daemon=True)
    x.start()


if __name__ == '__main__':
    main()