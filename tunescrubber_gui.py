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
from scipy.io import wavfile
from scipy.signal import hilbert, tukey
from sklearn import preprocessing
import PySimpleGUI as sg
import numpy as np
import simpleaudio as sa
import serial
import serial.tools.list_ports

GRAPH_SIZE = (400,300)
ANGLE_MAX = 3600
MAX_ENV_SAMPS = 1000

ser = serial.Serial()
ser.baudrate = 115200

playback_buffer = deque()
sample_rate = audio_buffer = num_channels = bytes_per_sample = None
playhead_position = 0
playhead_line = None
seconds_per_rotation = 1

torque_multiplier = 5000

envelope = None



ports_dropdown = sg.Combo((), readonly=True, size=(20, 5), key='Ports')
zoom_slider = sg.Slider(range=(1, 3), default_value=seconds_per_rotation, enable_events=True, orientation='horizontal', key='Zoom')
graph = sg.Graph(canvas_size=GRAPH_SIZE, graph_bottom_left=(0,0), graph_top_right=GRAPH_SIZE, key='Graph')
open_port = sg.Text('')
file_browse = sg.FileBrowse(button_text='Open File', key='File', file_types = (('.wav files', '*.wav'),), enable_events=True) 
position_indicator = sg.ProgressBar(max_value=3600, orientation='horizontal', key='position_indicator')
torque_slider = sg.Slider(range=(0, 25000), default_value=torque_multiplier, key='TorqueSlider', enable_events=True, orientation='horizontal')


sg.change_look_and_feel('LightGreen')
def window_function():
    global envelope, sample_rate, audio_buffer, num_channels, bytes_per_sample
    global torque_multiplier
    global seconds_per_rotation
    


    # sg.theme('DarkAmber')   # Add a touch of color
    # All the stuff inside your window.
    layout = [
        [sg.Text('Ports'), ports_dropdown, sg.Button('Refresh')],
        [sg.Button('Open Port', key='OpenButton'), open_port],
        [file_browse],
        [graph],
        [position_indicator],
        # [sg.Text('Zoom'), zoom_slider, sg.Button('Reset')],
        [sg.Text('Sensitivity'), torque_slider],
        [sg.Button('Clear')],
        [sg.Button('Quit')],
    ]
    # Create the Window
    window = sg.Window('TuneScrubber', [layout], resizable=True, finalize=True)
    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == 'Quit': # if user closes window or clicks cancel
            break
        elif event == 'OpenButton':
            port = values['Ports']
            ser.port = port
            if not ser.is_open:
                ser.open()
            open_port.update(f'Current port: {port}')
            window['OpenButton'].update(disabled=True)
        elif event == 'File':
            filepath = values['File']
            with wave.Wave_read(filepath) as w:
                bytes_per_sample = w.getsampwidth()
                num_channels = w.getnchannels()
            sample_rate, audio_buffer = wavfile.read(filepath)
            if num_channels > 1:
                audio_buffer = audio_buffer[:, 0] # quick hack to get mono signal
                num_channels = 1
            graph.erase()
            envelope = calc_envelope(audio_buffer)
            draw_envelope()
        elif event == 'Refresh':
            ports = serial.tools.list_ports.comports()
            ports_dropdown.update(values=[port for (port, desc, hwid) in ports])
        elif event == 'TorqueSlider':
            torque_multiplier = values['TorqueSlider']
        elif event == 'Clear':
            print('clearing canvas')
            envelope = None
            graph.erase()

            
    window.close()

def draw_envelope():
    w, h = GRAPH_SIZE
    # Draw envelope
    if envelope is not None:
        samples_per_pixel = len(envelope) // w
        for x in range(w-1):
            val = envelope[x * samples_per_pixel] * h * 200 # dirty hack to "normalize"
            graph.draw_line((x, 0), (x, val), color='white')

def draw_playhead():
    global playhead_line
    if envelope is None:
        return
    w, h = GRAPH_SIZE
    samples_per_pixel = len(envelope) // w
    if playhead_line is not None:
        graph.delete_figure(playhead_line)
    # Draw playhead
    x = playhead_position // samples_per_pixel
    playhead_line = graph.draw_line((x, 0), (x, h), color='red')


# Calculates the amplitude envelope of the audio file
def calc_envelope(buffer):
    if type(buffer[0]) == list:
        analytic_signal = np.abs(hilbert(buffer)[:, 0])
    else:
        analytic_signal = np.abs(hilbert(buffer))
    return analytic_signal / np.linalg.norm(analytic_signal)

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
        position_indicator.update(angle)
        # Angle goes from Quadrant 4 to Quadrant 1
        if angle < ANGLE_MAX // 4 and last_angle > (ANGLE_MAX // 4)*3:
            last_angle -= ANGLE_MAX
        # Angle goes from Quadrant 1 to Quadrant 4
        if angle > (ANGLE_MAX // 4)*3 and last_angle < ANGLE_MAX // 4:
            last_angle += ANGLE_MAX
        delta = last_angle - angle
        last_angle = angle
        if abs(delta) < 10:
            continue
        if delta >= 0:
            step = -1
        else:
            step = 1
        if audio_buffer is None:
            continue
        samples_per_delta_unit = int((sample_rate / ANGLE_MAX) * seconds_per_rotation)
        new_playhead_position = max(playhead_position - (delta*samples_per_delta_unit), 0)
        new_playhead_position = min(new_playhead_position, len(audio_buffer)-1)
        # The copy() is necessary so that everything is contiguous in memory.
        chunk = audio_buffer[playhead_position:new_playhead_position:step].copy(order='C')
        if len(chunk) == 0:
            continue
        envelope_chunk = envelope[playhead_position:new_playhead_position:step]
        avg_amplitude = np.mean(envelope_chunk)
        torque = int(avg_amplitude * torque_multiplier * step * -1)
        ser.write(f'{torque}'.encode('utf-8'))
        target_type = type(chunk[0])
        # Smooth the ends of the signal
        window = tukey(len(chunk), alpha=0.1)
        chunk = np.multiply(chunk, window).astype(target_type)
        playback_buffer.appendleft(chunk)
        playhead_position = new_playhead_position
        draw_playhead()

def playback_thread():
    global playback_buffer
    local_buffer = None
    while True:
        sleep(0.005)
        while playback_buffer:
            chunk = playback_buffer.pop()
            if local_buffer is None:
                local_buffer = chunk
            else:
                local_buffer = np.concatenate((local_buffer, chunk))
        if local_buffer is not None:
            sa.play_buffer(local_buffer, num_channels, bytes_per_sample, sample_rate)
            local_buffer = None


def reset_torque():
    if ser.is_open:
        ser.write(bytes(' 0' , 'utf-8'))


def main():
    atexit.register(reset_torque)
    threading.Thread(target=window_function).start()
    threading.Thread(target=serial_read_thread, daemon=True).start()
    threading.Thread(target=playback_thread, daemon=True).start()


if __name__ == '__main__':
    main()