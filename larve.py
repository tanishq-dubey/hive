#! /usr/bin/python3

# Need to do this first to avoid monkey patch errors
from gevent import monkey
monkey.patch_all()

import argparse
import logging
import fcntl
import hashlib
import json
import random
import socket
import struct
import sys
import threading
import time

from enum import Enum

import requests
import structlog
from flask import Flask, jsonify, request, abort
from gevent.pywsgi import WSGIServer


# Enum for holding status values
class Status(Enum):
    READY = 1
    NOT_READY = 2


# Enum for holding mode values
class Mode(Enum):
    DRONE = 1
    QUEEN = 2


# Create the Flask API server
app = Flask(__name__)

# Logger
log = structlog.get_logger()

# Default values
larve_status = Status.NOT_READY
larve_mode = Mode.DRONE
larve_verson = '0.0.1'

# A blank drone list
drones = dict()
drones_lock = threading.Lock()


# Function for the heartbeat thread
def queen_heartbeat():
    global drones
    global drones_lock

    max_retry = 5
    # We always want to be heartbeating
    while True:
        log.info("starting task", task="heartbeat")
        drones_lock.acquire()
        to_remove = []
        for k, v in drones.items():
            success = False
            count = 1
            while not success and count < max_retry:
                try:
                    log.info("heartbeating with drone", host=k, name=v)
                    requests.get(url='http://' + k + '/healthz')
                    success = True
                    log.info("got heartbeat with drone", host=k, name=v)
                except Exception:
                    log.warning("could not reach drone",
                                host=k,
                                name=v,
                                attempt=count,
                                max_attempt=max_retry)
                    count = count + 1
                    time.sleep(.5)
            if count >= max_retry:
                to_remove.append(k)
                log.warning("marking drone for removal", host=k, name=v)

        for r in to_remove:
            log.warning("removed drone from list", host=r)
            drones.pop(r, None)

        drones_lock.release()
        log.info("completed task", task="heartbeat")
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

    # If we are a queen, show the drones we know about
    if larve_mode == Mode.QUEEN:
        current_health['drones'] = drones

    return jsonify(current_health)


# Submit a task to the queen to be assigned to a drone
@app.route('/submit_task', methods=['POST'])
def submit_task():
    global drones
    global drones_lock

    # Input verification
    if not request.json or not 'text' in request.json:
        abort(400)
    if larve_mode == Mode.DRONE:
        abort(400, description='In drone mode, not scheduling tasks')
    task = request.json.get('text')

    # Send task to a drone...
    drones_lock.acquire()
    drone_host, drone_name = random.choice(list(drones.items()))
    payload = {"text": task}
    headers = {'Content-Type': 'application/json'}
    requests.post('http://' + drone_host + '/do_task',
                  headers=headers,
                  data=json.dumps(payload))
    log.info("sent task to drone", name=drone_name)
    drones_lock.release()

    return jsonify({'result': 'OK'})


# Register with the queen
@app.route('/register', methods=['POST'])
def register():
    global drones
    global drones_lock

    # Input verification
    if not request.json or not 'address' in request.json:
        abort(400)
    if larve_mode == Mode.DRONE:
        abort(400, description='In drone mode, not taking registration')

    drones_lock.acquire()
    name = str(hashlib.sha1(request.json.get('address').encode()).hexdigest())
    address = request.json.get('address')
    drones[address] = 'drone-' + name
    log.info("registered drone", name=name, host=address)
    drones_lock.release()

    return jsonify({'result': 'OK'})


# Endpoint for a drone to do work
# TODO: Add a header to make sure a queen sent it
@app.route('/do_task', methods=['POST'])
def do_task():
    if not request.json or not 'text' in request.json:
        abort(400)
    if larve_mode == Mode.QUEEN:
        abort(400, description='In queen mode, not taking tasks')
    task = request.json.get('text')
    if task:
        log.info("got task, replace with real task", task=task)
    else:
        abort(400)
    return jsonify({'result': 'OK'})


# Get the IP address of the interface the drone is running on
def get_ip_of_interface(interface_name):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(
        fcntl.ioctl(
            s.fileno(),
            0x8915,  # http://man7.org/linux/man-pages/man7/netdevice.7.html
            struct.pack('256s', interface_name[:15].encode('utf-8')))[20:24])


# Drone to queen registration
def register_with_queen(queen_host, interface_name, self_port):
    self_ip = get_ip_of_interface(interface_name)

    payload = {"address": self_ip + ":" + str(args.port)}
    headers = {'Content-Type': 'application/json'}
    registered = False

    # Keep trying to register
    while not registered:
        try:
            resp = requests.post('http://' + args.queenhost + '/register',
                                 headers=headers,
                                 data=json.dumps(payload))
            if resp.status_code > 299:
                log.error("could not register with queen",
                          queen=args.queenhost,
                          response=resp.text,
                          code=resp.status_code)
                sys.exit(-1)
            registered = True
        except Exception as e:
            log.warning('queen is not reachable, waiting',
                        queen=args.queenhost,
                        error=e)
            time.sleep(10)
    log.info("registered with queen", queen=args.queenhost)


if __name__ == "__main__":
    thread_list = []

    parser = argparse.ArgumentParser(description="Hive Larve Daemon")
    parser.add_argument("--queen",
                        dest="queen",
                        action="store_true",
                        help="Start this larve in queen mode")
    parser.add_argument(
        "--queen-host",
        dest="queenhost",
        required='--queen' not in sys.argv,
        help=
        "If running in drone mode, host and port of the queen to register with, example: 127.0.0.1:8080"
    )
    parser.add_argument(
        "--interface",
        dest="net_interface",
        required='--queen' not in sys.argv,
        help=
        "If running in drone mode, network interface the drone should use, example: enp5s0"
    )
    parser.add_argument("--port",
                        dest="port",
                        nargs="?",
                        const=1,
                        type=int,
                        default=8080,
                        help="Port to run on. Default 8080")
    parser.set_defaults(queen=False)
    args = parser.parse_args()

    # Set this here so we can start the API server and properly set mode
    if args.queen:
        larve_mode = Mode.QUEEN

    # Start APi server
    http_server = WSGIServer(('', args.port), app, log=None)
    http_thread = threading.Thread(target=http_server.serve_forever)
    http_thread.start()
    thread_list.append(http_thread)
    log.info("started thread", name="api-server")

    if args.queen:
        # Start queen heartbeating
        larve_mode = Mode.QUEEN
        heartbeat_thread = threading.Thread(target=queen_heartbeat)
        heartbeat_thread.start()
        thread_list.append(heartbeat_thread)
        log.info("started thread", name="queen-heartbeat")
    else:
        register_with_queen(args.queenhost, args.net_interface, args.port)

    larve_status = Status.READY

    for t in thread_list:
        t.join()
