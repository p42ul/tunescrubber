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


GRAPH_SIZE = (800,600)
GRAPH_STEP_SIZE = 5
ANGLE_MAX = 3600

ser = serial.Serial()
ser.baudrate = 115200

torque = 0

ports_dropdown = sg.Combo((), readonly=True, size=(20, 5), key='Ports')
torque_slider = sg.Slider(range=(-360, 360), default_value=0, enable_events=True, orientation='horizontal', key='Torque')
graph = sg.Graph(canvas_size=GRAPH_SIZE, graph_bottom_left=(0,0), graph_top_right=GRAPH_SIZE, key='Graph')
open_port = sg.Text('')

sg.change_look_and_feel('LightGreen')
def window_function():
    # sg.theme('DarkAmber')   # Add a touch of color
    # All the stuff inside your window.
    layout = [
        [sg.Text('Ports'), ports_dropdown, sg.Button('Refresh')],
        [sg.Button('Open'), open_port],
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
        elif event == 'Open':
            port = values['Ports']
            ser.port = port
            if not ser.is_open:
                ser.open()
            open_port.update(f'Current port: {port}')
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


def serial_read_thread():
    x = lastx = lasty = 0
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
        y = (angle/ANGLE_MAX) * GRAPH_SIZE[1]
        if x < GRAPH_SIZE[0]:
            graph.DrawLine((lastx, lasty), (x, y))
        else:
            graph.Move(-GRAPH_STEP_SIZE, 0)
            graph.DrawLine((lastx, lasty), (x, y))
            x -= GRAPH_STEP_SIZE
        lastx, lasty = x, y
        x += GRAPH_STEP_SIZE


def main():
    w = threading.Thread(target=window_function)
    w.start()
    x = threading.Thread(target=serial_read_thread)
    x.start()


if __name__ == '__main__':
    main()