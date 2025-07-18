import json
import logging
import atexit

from websocket_server import WebsocketServer
from threading import Thread

from ModulesController import ModulesController
from StatesManager import StatesManager


class BlendAction:
    Idle = 0
    Blend = 1
    Refill = 2


ADDR = "0.0.0.0"
PORT = 8765

current_action = BlendAction.Idle


def new_client(client, server):
    print("hi !")
    print(client)


def send_message(server, msg_type, data):
    server.send_message_to_all(json.dumps({
        'type': msg_type,
        'data': data
    }))


def thread_threat_message(client, server, message):
    t = Thread(target=threat_message, args=[client, server, message])
    t.start()


def if_not_busy(server, action, data=None, callback=None):
    if module_controller.remaining_blend_time > 0:
        send_message(server, 'error', {'msg': f'Busy ! Retry in {module_controller.remaining_blend_time} sec'})
    else:
        if callback:
            return action(data, callback)
        else:
            if data is not None:
                print("la !!!")
                return action(data)
            else:
                return action()


def threat_message(client, server, message):
    packet = json.loads(message)
    message_type = packet['type']
    # print(f"Recv {message_type} : {packet['data']}")

    def callback(data):
        send_message(server, 'status', data)
        print('status', data)

    print("msg : ", message_type)

    if message_type == 'echo':
        send_message(server, 'echo', packet)

    elif message_type == 'blend':
        if_not_busy(server, module_controller.blend, packet['data'], callback)
    elif message_type == 'faster_blend':
        if_not_busy(server, module_controller.faster_blend, packet['data'], callback)
    elif message_type == "get_blend_status":
        send_message(server, 'status', {"initial_time": module_controller.initial_blend_time, "remaining_time": module_controller.remaining_blend_time})

    elif message_type == "get_pumps_states":
        send_message(server, 'pumps_states', StatesManager().get_all_full_pump_states())
    elif message_type == "set_pump_state":
        pump_index = packet['data']['pump_index']
        state = packet['data']['state']
        StatesManager().set_pump_enabled(pump_index, state)

        send_message(server, 'pumps_states', StatesManager().get_all_full_pump_states())
    elif message_type == "set_sec_per_liter":
        sec_per_liter = packet['data']['sec_per_liter']
        StatesManager().set_sec_per_liter(sec_per_liter)
        send_message(server, 'sec_per_liter', StatesManager().get_sec_per_liter())
    elif message_type == "get_config":
        send_message(server, 'config', StatesManager().states)

    elif message_type == "set_pump_speed_ratio":
        pump_index = packet['data']['pump_index']
        speed_ratio = packet['data']['speed_ratio']
        StatesManager().set_pump_speed_ratio(pump_index, speed_ratio)
        send_message(server, 'config', StatesManager().states)

    elif message_type == "tare_cell":
        pump_index = packet['data']['pump_index']
        ok = if_not_busy(server, module_controller.tare_weight_cell, pump_index)
        if ok:
            send_message(server, "tare_cell", {"pump_index": pump_index})
    elif message_type == "tare_all_cell":
        ok = if_not_busy(server, module_controller.tare_all_cells)
        if ok:
            send_message(server, "tare_all_cell", {})

    elif message_type == "read_weight":
        pump_index = packet['data']['pump_index']
        ok = if_not_busy(server, module_controller.read_weight, pump_index)
        if ok:
            send_message(server, "read_weight", {"pump_index": pump_index})
    elif message_type == "read_all_weights":
        ok = if_not_busy(server, module_controller.read_all_weights)
        if ok:
            send_message(server, "read_all_weights", {})

    elif message_type == "get_all_weights":
        weights = if_not_busy(server, module_controller.get_all_weights)
        if weights:
            send_message(server, "get_all_weights", weights)

    else:
        send_message(server, 'unknown_message_type', {"message": f"given message type '{message_type}' is unknown"})


def main():
    server = WebsocketServer(host=ADDR, port=PORT, loglevel=logging.INFO)
    server.set_fn_new_client(new_client)
    server.set_fn_message_received(thread_threat_message)
    server.run_forever()


module_controller = ModulesController()
atexit.register(module_controller.cleanup)

main()
