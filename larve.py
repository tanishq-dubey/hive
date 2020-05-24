import argparse
import sys
from enum import Enum
import json
import random
import threading
import time

from flask import Flask, jsonify, request, abort
import requests

app = Flask(__name__)

# Enum for holding status values
class Status(Enum):
    READY = 1
    NOT_READY = 2

# Enum for holding mode values
class Mode(Enum):
    DRONE = 1
    QUEEN = 2

# Default values
larve_status = Status.NOT_READY 
larve_mode   = Mode.DRONE
larve_verson = '0.0.1'

# A blank drone list
drones = dict()
drones_lock = threading.Lock()


def queen_heartbeat():
    global drones
    global drones_lock

    max_retry = 5
    while True:
        print("Starting heartbeat")
        drones_lock.acquire()
        to_remove = []
        for k,v in drones.items():
            success = False
            count = 1
            while not success and count < max_retry:
                try:
                    print(f"checking {k} ({v})")
                    requests.get(url= 'http://' + k + '/healthz')
                    success = True
                    print(f"check-in from {k} ({v})")
                except Exception:
                    print(f"could not check {k} ({v}) on attempt {count}/{max_retry}")
                    count = count + 1
                    time.sleep(.5)
            if count >= max_retry:
                to_remove.append(k)
                print(f"marking {k} ({v}) for removal from drone list")
                print(drones)

        for r in to_remove:
            print(f"removed {r} from drone list")
            drones.pop(r, None)

        drones_lock.release()
        time.sleep(10)


# What to do on '/healthz'
@app.route('/healthz', methods=['GET'])
def healthz():
    global drones
    current_health = {
        "status": str(larve_status),
        "version": larve_verson,
        "mode": str(larve_mode)
    }

    if larve_mode == Mode.QUEEN:
        current_health['drones'] = drones

    return jsonify(current_health)


@app.route('/submit_task', methods=['POST'])
def submit_task():
    global drones
    global drones_lock
    if not request.json or not 'text' in request.json:
        abort(400)
    if larve_mode == Mode.DRONE:
        abort(400, description='In drone mode, not scheduling tasks')
    task = request.json.get('text')

    # Send task to a drone...
    drones_lock.acquire()
    drone_host, drone_name = random.choice(list(drones.items()))
    payload = { "text": task }
    headers = { 'Content-Type': 'application/json' }
    requests.request("POST", 'http://' + drone_host + '/do_task', headers=headers, data=json.dumps(payload))
    print(f"Sent task to {drone_name}")
    drones_lock.release()

    return jsonify({'result': 'OK'})

@app.route('/register', methods=['POST'])
def register():
    global drones
    global drones_lock
    if not request.json or not 'address' in request.json:
        abort(400)
    if larve_mode == Mode.DRONE:
        abort(400, description='In drone mode, not taking registration')

    drones_lock.acquire()
    drones[request.json.get('address')] = 'drone-' + str(len(drones))
    drones_lock.release()

    return jsonify({'result': 'OK'})


@app.route('/do_task', methods=['POST'])
def do_task():
    if not request.json or not 'text' in request.json:
        abort(400)
    if larve_mode == Mode.QUEEN:
        abort(400, description='In queen mode, not taking tasks')
    task = request.json.get('text')
    if task:
        print(task)
    else:
        abort(400)
    return jsonify({'result': 'OK'})

if __name__ == '__main__':
    # When we start, set our status
    parser = argparse.ArgumentParser(description='Hive Larve Daemon')
    parser.add_argument("--queen", dest='queen', action='store_true', help="Start this larve in queen mode")
    parser.add_argument("--queen-host", dest='queenhost', required='--queen' not in sys.argv, help="If running in drone mode, host and port of the queen to register with, example: 127.0.0.1:8080")
    parser.add_argument("--port", dest='port', nargs='?', const=1, type=int, default=8080, help="Port to run on, default 8080")
    parser.set_defaults(queen=False)
    args = parser.parse_args()
    flask_thread = threading.Thread(target=app.run, kwargs={'port': args.port})
    flask_thread.start()
    heartbeat_thread = threading.Thread(target=queen_heartbeat)

    if args.queen:
        larve_mode = Mode.QUEEN
        heartbeat_thread.start()
    else:
        payload = { "address": "127.0.0.1:" + str(args.port) }
        headers = { 'Content-Type': 'application/json' }
        resp = requests.request("POST", 'http://' + args.queenhost + '/register', headers=headers, data = json.dumps(payload))
        if resp.status_code > 299:
            print("Could not register to queen")
            sys.exit(-1)
        print(f"Registered to {args.queenhost}")

    larve_status = Status.READY


    flask_thread.join()
    if args.queen:
        heartbeat_thread.join()
