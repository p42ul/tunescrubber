# TuneScrubber -- haptic feedback for audio files
# Some graph code borrwed from https://linuxtut.com/en/dc72976987d7ef485df1/


# Standard libraries
from time import sleep
import logging
import threading

# Third-party libraries
from scipy.io import wavfile
from scipy.signal import hilbert
from sklearn import preprocessing
import PySimpleGUI as sg
import numpy as np
import serial
import serial.tools.list_ports
from scipy.signal import hilbert
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.pyplot import figure, show 
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('TkAgg')

GRAPH_SIZE = (400,300)
ANGLE_MAX = 3600
MAX_ENV_SAMPS = 1000

ser = serial.Serial()
ser.baudrate = 115200

torque = 0

ports_dropdown = sg.Combo((), readonly=True, size=(20, 5), key='Ports')
zoom_slider = sg.Slider(range=(0, 100), default_value=0, enable_events=True, orientation='horizontal', key='Torque')
canvas = sg.Canvas(key='Canvas')
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
        [canvas],
        [sg.Text('Zoom'), zoom_slider, sg.Button('Reset')],
        [sg.Button('Quit')],
    ]
    # Create the Window
    window = sg.Window('Serial Communicator', [layout], resizable=True, finalize=True)

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
            sample_rate, audio_buffer = wavfile.read(values['File'])
            envelope = calc_envelope(audio_buffer)
            plt.clf()
            envPlot.plot(envelope)
            fig_canvas_agg = draw_figure(fig_canvas_agg)
        elif event == 'Refresh':
            ports = serial.tools.list_ports.comports()
            ports_dropdown.update(values=[port for (port, desc, hwid) in ports])
        elif event == 'Zoom':
            torque = values['Zoom']
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
    analytic_signal = np.abs(hilbert(buffer)[:, 0])
    return analytic_signal / np.linalg.norm(analytic_signal)

def draw_figure(figure_canvas_agg):
    figure_canvas_agg.draw()
    figure_canvas_agg.get_tk_widget().pack(side='top', fill='both', expand=1)
    return figure_canvas_agg

class ZoomPan:
    def __init__(self):
        self.cur_xlim = None
        self.cur_ylim = None
        self.x0 = None
        self.y0 = None
        self.x1 = None
        self.y1 = None

    def zoom_factory(self, ax, base_scale = 2.):
        def zoom(event):
            cur_xlim = ax.get_xlim()
            cur_ylim = ax.get_ylim()

            xdata = event.xdata # get event x location
            ydata = event.ydata # get event y location

            if event.button == 'up':
                # deal with zoom in
                scale_factor = 1 / base_scale
            elif event.button == 'down':
                # deal with zoom out
                scale_factor = base_scale
            else:
                # deal with something that should never happen
                scale_factor = 1
                print (event.button)

            new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
            new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor

            relx = (cur_xlim[1] - xdata)/(cur_xlim[1] - cur_xlim[0])
            rely = (cur_ylim[1] - ydata)/(cur_ylim[1] - cur_ylim[0])

            ax.set_xlim([xdata - new_width * (1-relx), xdata + new_width * (relx)])
            ax.set_ylim([ydata - new_height * (1-rely), ydata + new_height * (rely)])
            ax.figure.canvas.draw()

        fig = ax.get_figure() # get the figure of interest
        fig.canvas.mpl_connect('scroll_event', zoom)

        return zoom

    def pan_factory(self, ax):
        def onPress(event):
            if event.inaxes != ax: return
            self.cur_xlim = ax.get_xlim()
            self.cur_ylim = ax.get_ylim()
            self.press = self.x0, self.y0, event.xdata, event.ydata
            self.x0, self.y0, self.xpress, self.ypress = self.press

        def onRelease(event):
            self.press = None
            ax.figure.canvas.draw()

        def onMotion(event):
            if self.press is None: return
            if event.inaxes != ax: return
            dx = event.xdata - self.xpress
            dy = event.ydata - self.ypress
            self.cur_xlim -= dx
            self.cur_ylim -= dy
            ax.set_xlim(self.cur_xlim)
            ax.set_ylim(self.cur_ylim)

            ax.figure.canvas.draw()

        fig = ax.get_figure() # get the figure of interest

        # attach the call back
        fig.canvas.mpl_connect('button_press_event',onPress)
        fig.canvas.mpl_connect('button_release_event',onRelease)
        fig.canvas.mpl_connect('motion_notify_event',onMotion)

        #return the function
        return onMotion

def serial_read_thread():
    absolute_position = None
    last_angle = None
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
        if absolute_position is None:
            absolute_position = angle
            last_angle = angle
        else:
            # Angle goes from Quadrant 4 to Quadrant 1
            if angle < ANGLE_MAX // 4 and last_angle > (ANGLE_MAX // 4)*3:
                last_angle -= ANGLE_MAX
            # Angle goes from Quadrant 1 to Quadrant 4
            if angle > (ANGLE_MAX // 4)*3 and last_angle < ANGLE_MAX // 4:
                last_angle += ANGLE_MAX
            absolute_position += (last_angle - angle)
            last_angle = angle
        print(absolute_position)


def main():
    w = threading.Thread(target=window_function)
    w.start()
    x = threading.Thread(target=serial_read_thread, daemon=True)
    x.start()


if __name__ == '__main__':
    main()