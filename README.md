# "Kubernetes" The Hardest Way
Also known as: Writing your own version of Kubernetes, _Hive_.


## Part 1: A Simple Agent

At the base of Kubernetes, there is an agent: the Kubelet. The Kubelet resides on every node in a Kubernetes
cluster and manages what occurs on that node. We begin by writing our own Kubelet. Since we are basing all
of our terms off Bee Hives, ours will be called a Larve.

### Larve

Our Larve, or the daemon running on every node, is essentially an HTTP server.
It exposes an API, and based on the requests that come into this API, it does
things on the node. In our case, starting and stopping containers. Since we are
writing a very simple version of Kubernetes, we can get away with using JSON on
our API, rather something more efficicent like Protobuf.

Let's begin by writing the most basic Larve, one that does two things:

 - A heartbeat endpoint, let's keep it standard and call it '/healthz'
    - Returns Larve version
    - Returns Larve status
  - A 'do task' endpoint, for now lets just have the Larve print a value
    given to it
    - Body: `{ "text": "hello"}` -> Larve prints "hello" to console

To implement this, lets use Flask -- it's fairly standard, easy to use, and
although some might argue it is heavy, it gets our job done:

```python
from flask import Flask, jsonify, request, abort
from enum import Enum

app = Flask(__name__)

# Enum for holding status values
class Status(Enum):
    READY = 1
    NOT_READY = 2

# Default values
larve_status = Status.NOT_READY 
larve_verson = '0.0.1'

# What to do on '/healthz'
@app.route('/healthz', methods=['GET'])
def healthz():
    current_health = {
        "status": str(larve_status),
        "version": larve_verson
    }
    return jsonify(current_health)

@app.route('/do_task', methods=['POST'])
def do_task():
    if not request.json or not 'text' in request.json:
        abort(400)
    task = request.json.get('text')
    if task:
        print(task)
    else:
        abort(400)
    return jsonify({'result': 'OK'})

if __name__ == '__main__':
    # When we start, set our status
    larve_status = Status.READY
    app.run(debug=True)
```

Great. We have a simple Larve here. We can see that when we call the '/healthz'
endpoint, we get our Larve status:

```bash
➜  ~ curl localhost:5000/healthz
{
  "status": "Status.READY",
  "version": "0.0.1"
}
```

And upon calling the `/do_task` endpoint, we get something printed to the console:

```bash
➜  ~ curl --location --request POST 'localhost:5000/do_task' \
--header 'Content-Type: application/json' \
--data-raw '{
        "text": "hello"
}'

{
  "result": "OK"
}
```

And in the Larve console:

```log
hello
127.0.0.1 - - [10/May/2020 00:30:33] "POST /do_task HTTP/1.1" 200 -
```

Ok, so we have something that's not so useful, but it is a critical building block
for our "Hive" system.  You see, this is basically what the Kubernetes Kubelet is:
A tiny application that maintains/reports it's status and takes orders from some
higher authority, which is....the kubelet. Specifically, we will change our larve
to become one of two things: a drone, the worker unit, or a queen, the commmanding
unit.
