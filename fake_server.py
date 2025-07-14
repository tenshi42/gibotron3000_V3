import json
import logging
import time
from threading import Thread, Lock

from websocket_server import WebsocketServer

# --- Configuration ---
HOST = "0.0.0.0"
PORT = 8765

# --- Simulated State ---
# This dictionary holds the entire state of our simulated machine.
# It's what the real server would manage in its StatesManager and ModulesController.
simulated_state = {
    "pumps": [
        {"enabled": True, "speed_ratio": 1.0, "weight": 500.0},
        {"enabled": True, "speed_ratio": 1.0, "weight": 500.0},
        {"enabled": True, "speed_ratio": 1.0, "weight": 500.0},
        {"enabled": True, "speed_ratio": 1.0, "weight": 500.0},
        {"enabled": True, "speed_ratio": 1.0, "weight": 500.0},
        {"enabled": True, "speed_ratio": 1.0, "weight": 500.0},
        {"enabled": False, "speed_ratio": 1.0, "weight": 500.0},
        {"enabled": True, "speed_ratio": 1.0, "weight": 500.0},
    ],
    "sec_per_liter": 300,
    "blend_status": {
        "initial_time": 0,
        "remaining_time": 0,
    }
}
# A lock to prevent race conditions when multiple clients modify the state
state_lock = Lock()


# --- Helper Functions ---

def send_message(server, client, msg_type, data):
    """Sends a JSON message to a specific client."""
    payload = json.dumps({'type': msg_type, 'data': data})
    server.send_message(client, payload)


def broadcast_message(server, msg_type, data):
    """Sends a JSON message to all connected clients."""
    payload = json.dumps({'type': msg_type, 'data': data})
    server.send_message_to_all(payload)


def is_busy():
    """Checks if a blocking action (like blending) is in progress."""
    return simulated_state["blend_status"]["remaining_time"] > 0


# --- Blending Simulation ---

def blend_simulation(server, data, faster=False):
    """
    Simulates the blending process in a separate thread.
    This is a "blocking action".
    """
    with state_lock:
        if is_busy():
            # This check is technically redundant if `if_not_busy` is used,
            # but it's good practice for thread safety.
            return

        cup_size = data.get("cup_size", 0)
        # Calculate total blend time. Faster blend is 30% quicker.
        total_time = int(cup_size * simulated_state["sec_per_liter"])
        if faster:
            total_time = int(total_time * 0.7)

        simulated_state["blend_status"]["initial_time"] = total_time
        simulated_state["blend_status"]["remaining_time"] = total_time

    # Blending loop
    while True:
        with state_lock:
            remaining = simulated_state["blend_status"]["remaining_time"]
            if remaining <= 0:
                simulated_state["blend_status"]["initial_time"] = 0
                # Send final status
                broadcast_message(server, 'status', simulated_state["blend_status"])
                break

            # Send periodic status update
            broadcast_message(server, 'status', simulated_state["blend_status"])
            simulated_state["blend_status"]["remaining_time"] -= 1

        time.sleep(1)
    print("Blend finished.")


# --- WebSocket Server Callbacks ---

def new_client(client, server):
    """Called for every new client that connects."""
    print(f"New client connected: {client['id']}")
    # You could send an initial state to the new client here if needed
    # send_message(server, client, 'config', simulated_state)


def client_left(client, server):
    """Called for every client that disconnects."""
    print(f"Client disconnected: {client['id']}")


def message_received(client, server, message):
    """
    Called when a message is received from a client.
    This is the main message router.
    """
    print(f"Received message from {client['id']}: {message}")
    try:
        packet = json.loads(message)
        msg_type = packet.get('type')
        data = packet.get('data', {})
    except (json.JSONDecodeError, AttributeError):
        send_message(server, client, 'error', {'msg': 'Invalid JSON format.'})
        return

    # --- Message Handling ---

    # This wrapper ensures blocking actions don't overlap.
    def if_not_busy(action, *args):
        if is_busy():
            send_message(server, client, 'error',
                         {'msg': f'Busy! Retry in {simulated_state["blend_status"]["remaining_time"]} sec'})
        else:
            action(*args)

    with state_lock:
        if msg_type == 'echo':
            send_message(server, client, 'echo', data)

        elif msg_type == 'blend':
            thread = Thread(target=if_not_busy, args=(blend_simulation, server, data, False))
            thread.start()

        elif msg_type == 'faster_blend':
            thread = Thread(target=if_not_busy, args=(blend_simulation, server, data, True))
            thread.start()

        elif msg_type == 'get_blend_status':
            send_message(server, client, 'status', simulated_state["blend_status"])

        elif msg_type == 'get_pumps_states':
            # Create a simplified version for the client as per the README
            pump_states = [{"enabled": p["enabled"]} for p in simulated_state["pumps"]]
            send_message(server, client, 'pumps_states', pump_states)

        elif msg_type == 'set_pump_state':
            pump_index = data.get('pump_index')
            state = data.get('state')
            if pump_index is not None and 0 <= pump_index < len(simulated_state["pumps"]):
                simulated_state["pumps"][pump_index]["enabled"] = bool(state)
                pump_states = [{"enabled": p["enabled"]} for p in simulated_state["pumps"]]
                broadcast_message(server, 'pumps_states', pump_states)  # Broadcast change to all clients
            else:
                send_message(server, client, 'error', {'msg': 'Invalid pump index.'})

        elif msg_type == 'set_sec_per_liter':
            simulated_state['sec_per_liter'] = int(data.get('sec_per_liter', 300))
            broadcast_message(server, 'sec_per_liter', simulated_state['sec_per_liter'])

        elif msg_type == 'get_config':
            send_message(server, client, 'config', simulated_state)

        elif msg_type == 'set_pump_speed_ratio':
            pump_index = data.get('pump_index')
            speed_ratio = data.get('speed_ratio')
            if pump_index is not None and 0 <= pump_index < len(simulated_state["pumps"]):
                simulated_state["pumps"][pump_index]["speed_ratio"] = float(speed_ratio)
                broadcast_message(server, 'config', simulated_state)  # Broadcast change
            else:
                send_message(server, client, 'error', {'msg': 'Invalid pump index.'})

        # --- Weight Cell Simulation ---
        elif msg_type == 'tare_cell':
            if_not_busy(lambda: send_message(server, client, 'tare_cell', {'pump_index': data.get('pump_index')}))

        elif msg_type == 'tare_all_cell':
            if_not_busy(lambda: send_message(server, client, 'tare_all_cell', {}))

        elif msg_type == 'read_weight':
            if_not_busy(lambda: send_message(server, client, 'read_weight', {'pump_index': data.get('pump_index')}))

        elif msg_type == 'read_all_weights':
            if_not_busy(lambda: send_message(server, client, 'read_all_weights', {}))

        elif msg_type == 'get_all_weights':
            weights = {str(i): p["weight"] for i, p in enumerate(simulated_state["pumps"])}
            if_not_busy(lambda: send_message(server, client, 'get_all_weights', weights))

        elif msg_type == 'set_weight':
            pump_index = data.get('pump_index')
            weight = data.get('weight')
            if pump_index is not None and 0 <= pump_index < len(simulated_state["pumps"]) and weight is not None:
                simulated_state["pumps"][pump_index]["weight"] = float(weight)
                weights = {str(i): p["weight"] for i, p in enumerate(simulated_state["pumps"])}
                broadcast_message(server, 'get_all_weights', weights)
            else:
                send_message(server, client, 'error', {'msg': 'Invalid pump index or missing weight.'})

        elif msg_type == 'set_all_weights':
            weight = data.get('weight')
            if weight is not None:
                for pump in simulated_state["pumps"]:
                    pump["weight"] = float(weight)
                weights = {str(i): p["weight"] for i, p in enumerate(simulated_state["pumps"])}
                broadcast_message(server, 'get_all_weights', weights)
            else:
                send_message(server, client, 'error', {'msg': 'Missing weight.'})

        else:
            send_message(server, client, 'unknown_message_type',
                         {'message': f"given message type '{msg_type}' is unknown"})


# --- Main Execution ---
if __name__ == "__main__":
    server = WebsocketServer(host=HOST, port=PORT, loglevel=logging.INFO)
    server.set_fn_new_client(new_client)
    server.set_fn_client_left(client_left)
    server.set_fn_message_received(message_received)

    print(f"Starting AutoBarMaid simulator on ws://{HOST}:{PORT}")
    server.run_forever()
