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
import math

from enum import Enum

import requests
import structlog
from flask import Flask, jsonify, request, abort, Response
from gevent.pywsgi import WSGIServer


# Enum for holding status values
class Status(Enum):
    READY = 1
    NOT_READY = 2


# Enum for holding mode values
class Mode(Enum):
    DRONE = 1
    QUEEN = 2


# A member of a Raft group can be in one of three states
# Everyone starts in the follower state
class RaftState(Enum):
    FOLLOWER = 1
    CANDIDATE = 2
    LEADER = 3


# Create the Flask API server
app = Flask(__name__)

# Logger
log = structlog.get_logger()

# Default values
larve_status = Status.NOT_READY
larve_mode = Mode.DRONE
larve_verson = '0.0.1'
interface = ""

# Our leader timeout is anywhere between 5 and 15 seconds
raft_election_timeout = random.randint(150, 300)
raft_state = RaftState.FOLLOWER
raft_term = 0
raft_lock = threading.Lock()

# A blank drone list
drones = dict()
drones_lock = threading.Lock()

# A blank queen list
queens = []


def get_time_millis():
    return int(round(time.time() * 1000))


# The unix time (in seconds) we last heard from someone
last_heartbeat = get_time_millis()


# Function for the heartbeat thread
def queen_heartbeat():
    global drones
    global drones_lock

    max_retry = 5
    # We always want to be heartbeating
    while True:
        if raft_state == RaftState.LEADER:
            drones_lock.acquire()
            to_remove = []
            for k, v in drones.items():
                success = False
                count = 1
                while not success and count < max_retry:
                    try:
                        log.info("heartbeating with drone", host=k, name=v)
                        send_heartbeat(k)
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
        time.sleep(10)


def raft():
    global raft_state
    global raft_term
    global raft_lock
    global last_heartbeat
    global raft_election_timeout

    # We're always doing raft
    while True:

        if raft_state == RaftState.FOLLOWER:
            if (get_time_millis() - last_heartbeat) > raft_election_timeout:
                raft_state = RaftState.CANDIDATE
                log.info("Changing raft state", previous=str(RaftState.FOLLOWER), next=str(RaftState.CANDIDATE))
            else:
                time.sleep(10/1000.0)

        if raft_state == RaftState.CANDIDATE:
            log.info("starting vote pool")
            raft_election_timeout = random.randint(150,300)
            raft_lock.acquire()
            raft_term = raft_term + 1
            raft_lock.release()
            num_votes = sum(do_list_threaded(send_vote_request_thread, queens))
            # Vote for ourselves
            num_votes = num_votes + 1
            last_heartbeat = get_time_millis()
            votes_needed = int(math.ceil((len(queens) + 1)/2.0))
            log.info("got votes", count = num_votes, needed=votes_needed, term=raft_term)

            # If we had aborted the election early, then we can ignore all our votes
            raft_lock.acquire()
            if raft_state == RaftState.FOLLOWER:
                num_votes = 0
            raft_lock.release()

            # Check to see if we have a majority of votes
            raft_lock.acquire()
            if num_votes > votes_needed:
                log.info("Changing raft state", previous=str(RaftState.CANDIDATE), next=str(RaftState.LEADER))
                raft_state = RaftState.LEADER
            else:
                log.info("Changing raft state", previous=str(RaftState.CANDIDATE), next=str(RaftState.FOLLOWER))
                raft_state = RaftState.FOLLOWER
            raft_lock.release()
        if raft_state == RaftState.LEADER:
            do_list_threaded(send_append_entries_thread, queens)
            time.sleep(100/1000.0)


def do_list_threaded(func, to_do):
    ret_list = [0] * len(to_do)
    do_thread_list = []
    for i in range(len(to_do)):
        t = threading.Thread(target=func, args=[to_do[i], i, ret_list])
        t.start()
        do_thread_list.append(t)

    for t in do_thread_list:
        t.join()

    return ret_list


def send_heartbeat_thread(host, idx, ret_list):
    send_heartbeat(host)


def send_heartbeat(host):
    try:
        requests.get(url='http://' + host + '/healthz')
    except Exception:
        log.warning("could not reach larve to heartbeat",
                    host=host)


# What to do on '/healthz'
@app.route('/healthz', methods=['GET'])
def healthz():
    global drones
    global last_heartbeat

    last_heartbeat = get_time_millis()

    current_health = {
        "status": str(larve_status),
        "version": larve_verson,
        "mode": str(larve_mode),
        "last_heartbeat": last_heartbeat
    }

    # If we are a queen, show the drones we know about
    # We also care about the raft state
    if larve_mode == Mode.QUEEN:
        current_health['drones'] = drones
        current_health['raft_state'] = str(raft_state)


    return jsonify(current_health)


def send_append_entries_thread(host, idx, ret_list):
     send_append_entries(host)


def send_append_entries(host):
    self_ip = get_ip_of_interface(interface)
    payload = {
        "leader": self_ip + ":" + str(args.port),
        "term": raft_term,
        "entries": []
        }
    headers = {'Content-Type': 'application/json'}
    try:
        requests.post('http://' + host + '/append_entries',
                             headers=headers,
                             data=json.dumps(payload))
    except Exception as e:
        pass


@app.route('/append_entries', methods=['POST'])
def append_entries():
    global raft_term
    global raft_state
    global raft_lock
    global last_heartbeat

    if not request.json or not 'leader' in request.json:
        abort(400)
    if not request.json or not 'term' in request.json:
        abort(400)
    if not request.json or not 'entries' in request.json:
        abort(400)

    raft_lock.acquire()
    if raft_state == RaftState.CANDIDATE:
        # We are a candidate and we got an append entries
        entry_term = int(request.json.get('term'))
        leader = request.json.get('leader')
        if entry_term >= raft_term:
            log.info("Aborting candidate state", term=entry_term, leader=leader)
            last_heartbeat = get_time_millis()
            raft_term = entry_term
            raft_state = RaftState.FOLLOWER
            log.info("Changing raft state", previous=str(RaftState.CANDIDATE), next=str(RaftState.FOLLOWER))
            raft_lock.release()
            return jsonify({'result': 'OK'})
        else:
            raft_lock.release()
            abort(400)

    # If we had entries, do stuff with them here
    last_heartbeat = get_time_millis()
    raft_lock.release()
    return jsonify({'result': 'OK'})


def send_vote_request_thread(voter_queen, idx, ret_list):
    val = send_vote_request(voter_queen)
    ret_list[idx] = val


def send_vote_request(voter_queen):
    global raft_term

    log.info("sending vote request", queen=voter_queen, term=raft_term)
    self_ip = get_ip_of_interface(interface)
    payload = {
            "candidate": self_ip + ":" + str(args.port),
            "term" : raft_term
            }
    headers = {'Content-Type': 'application/json'}

    try:
        resp = requests.post('http://' + voter_queen + '/request_vote',
                             headers=headers,
                             data=json.dumps(payload))
    except Exception as e:
        log.error("could request vote with queen",
                  queen=voter_queen,
                  error=e)
        return 0

    if resp.status_code > 399:
        log.error("could request vote with queen",
                  queen=voter_queen,
                  response=resp.text,
                  code=resp.status_code)
        return 0

    if resp.status_code > 299:
        log.info("queen rejected vote",
                 queen=voter_queen)
        return 0

    log.info("got vote from queen", queen=voter_queen)

    return 1


@app.route('/request_vote', methods=['POST'])
def request_vote():
    global last_heartbeat
    global raft_term
    global raft_lock

    last_heartbeat = get_time_millis()

    if not request.json or not 'candidate' in request.json:
        abort(400)

    if not request.json or not 'term' in request.json:
        abort(400)

    candidate = request.json.get('candidate')
    term = request.json.get('term')

    raft_lock.acquire()
    log.info("got request for vote", candidate=candidate, term=term, current_term=raft_term)
    if term > raft_term:
        raft_term = term
        raft_lock.release()
        return jsonify({'result': 'OK'})

    raft_lock.release()
    return Response("{'reason': 'invalid term'}", status=300, mimetype='application/json')


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
        "--queen-list",
        dest="queenlist",
        nargs='+',
        required='--queen' in sys.argv,
        help=
        "If running in queen mode, list of all the queens, example: 127.0.0.1:8081 127.0.0.1:8082..."
    )
    parser.add_argument(
        "--interface",
        dest="net_interface",
        required=True,
        help=
        "Network interface the larve should use, example: enp5s0"
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

    interface = args.net_interface

    # Start APi server
    http_server = WSGIServer(('', args.port), app, log=None)
    http_thread = threading.Thread(target=http_server.serve_forever)
    http_thread.start()
    thread_list.append(http_thread)
    log.info("started thread", name="api-server", port=args.port)

    if args.queen:
        queens = args.queenlist
        log.info("in queen mode", queen_list=queens)

        # Start building a raft with other queens
        raft_state = RaftState.FOLLOWER
        raft_thread = threading.Thread(target=raft)

        # Start queen heartbeating
        larve_mode = Mode.QUEEN
        heartbeat_thread = threading.Thread(target=queen_heartbeat)

        raft_thread.start()
        heartbeat_thread.start()

        thread_list.append(raft_thread)
        log.info("started thread", name="raft", election_timeout=raft_election_timeout)
        thread_list.append(heartbeat_thread)
        log.info("started thread", name="queen-heartbeat")
    else:
        register_with_queen(args.queenhost, args.net_interface, args.port)

    larve_status = Status.READY

    for t in thread_list:
        t.join()
