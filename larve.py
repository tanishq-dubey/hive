import argparse

from flask import Flask, jsonify, request, abort
from enum import Enum

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

# What to do on '/healthz'
@app.route('/healthz', methods=['GET'])
def healthz():
    current_health = {
        "status": str(larve_status),
        "version": larve_verson,
        "mode": str(larve_mode)
    }
    return jsonify(current_health)


@app.route('/submit_task', methods=['POST'])
def submit_task():
    if not request.json or not 'text' in request.json:
        abort(400)
    if larve_mode == Mode.DRONE:
        abort(400, description='In drone mode, not scheduling tasks')
    task = request.json.get('text')
    # Send task to a drone...
    return jsonify({'result': 'OK'})

@app.route('/register', methods=['POST'])
def register():
    global drones
    if not request.json or not 'address' in request.json:
        abort(400)
    if larve_mode == Mode.DRONE:
        abort(400, description='In drone mode, not taking registration')
    drones[request.json.get('address')] = 'drone-' + str(len(drones))
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
    parser.add_argument("--queen", dest='queen', action='store_true')
    parser.set_defaults(queen=False)
    args = parser.parse_args()

    if args.queen:
        larve_mode = Mode.QUEEN
    larve_status = Status.READY
    app.run(debug=True)
