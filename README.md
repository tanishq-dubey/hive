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

## Part 2: Of Drones and Queens

Now, while it sounds confusing that a single program can both control and do work,
it isn't that crazy. You see, the kubelet is a standard application across all Kubernetes nodes
both workers and master nodes. When the kubelet starts up, it looks at its configuration to see
what type of node it is, and behaves accordingly. Masters are the ones that dispatch orders
and the nodes are the ones that do the work. We will have the same with _drones_ and _queens_.

We can modify our current Larve to have the same behavior. We begin by adding
a `Mode` enum:

```diff
diff --git a/larve.py b/larve.py
index c470f2a..cecb003 100644
--- a/larve.py
+++ b/larve.py
@@ -8,6 +8,11 @@ class Status(Enum):
     READY = 1
     NOT_READY = 2

+# Enum for holding mode values
+class Mode(Enum):
+    DRONE = 1
+    QUEEN = 2
+
 # Default values
 larve_status = Status.NOT_READY
 larve_verson = '0.0.1'
```

Our two modes will be `DRONE`, or a worker, and `QUEEN` or a master. However, before
we get to modifying our Larve to turn into drones or queens, we should define the
responsibilities they will have:

Queens
- Maintain state of the Hive
   - Know who all the Drones are
   - Know what all the Drones are doing
   - Know if a Drone can do more work
 - Take in requests to do things on the Hive
 - Instruct Drones to do required tasks

Drones
 - Maintain state of themselves
   - Know who they are
   - Know what they are doing
   - Know if they can do more work
 - Take in requests to do a task (from a Queen)
 - Do given tasks


With this list of duties we can see that Drones are quite dumb. They only care about
themselves and nothing else. In order for a drone to be useful in any way, there must
be a queen ordering the drone to do something. With this in mind, we can delcare that
the simplest Hive would consist of one queen and one drone. The user would interface
with the queen to provide tasks, and the queen would hand those tasks to the drone.
Do note that the queen is not doing any work here. All the queen is responsible for is
maintining the state of the Hive, and like in stereotypical royal fashion, not doing
the dirty work. Let's begin our work by finishing the Drone implementation, since we
are nearly done with it:

```diff
diff --git a/larve.py b/larve.py
index cecb003..e0b3fd3 100644
--- a/larve.py
+++ b/larve.py
@@ -1,3 +1,5 @@
+import argparse
+
 from flask import Flask, jsonify, request, abort
 from enum import Enum

@@ -15,6 +17,7 @@ class Mode(Enum):

 # Default values
 larve_status = Status.NOT_READY
+larve_mode   = Mode.DRONE
 larve_verson = '0.0.1'

 # What to do on '/healthz'
@@ -22,7 +25,8 @@ larve_verson = '0.0.1'
 def healthz():
     current_health = {
         "status": str(larve_status),
-        "version": larve_verson
+        "version": larve_verson,
+        "mode": str(larve_mode)
     }
     return jsonify(current_health)

@@ -30,6 +34,8 @@ def healthz():
 def do_task():
     if not request.json or not 'text' in request.json:
         abort(400)
+    if larve_mode == Mode.QUEEN:
+        abort(400, description='In queen mode, not taking tasks')
     task = request.json.get('text')
     if task:
         print(task)
@@ -39,5 +45,12 @@ def do_task():

 if __name__ == '__main__':
     # When we start, set our status
+    parser = argparse.ArgumentParser(description='Hive Larve Daemon')
+    parser.add_argument("--queen", dest='queen', action='store_true')
+    parser.set_defaults(queen=False)
+    args = parser.parse_args()
+
+    if args.queen:
+        larve_mode = Mode.QUEEN
     larve_status = Status.READY
     app.run(debug=True)
```

Our changes are quite minor. Probably the most visible change is the usage of
the `argparse` library, which will make it simple to switch between queen and
drone mode. By default, we begin in drone mode, and if the `--queen` flag is
provided at startup, we switch into queen mode. The next change is the inclusion
of the mode in our `/healthz` endpoint. Finally, we change our `/do_task`
implementation such that if we are in queen mode, we don't do work, that is just
for drones.

Moving on to the queen implementation, we need to add a few items to our larve.
First, we should add a `submit_task` endpoint. This will be the external API
that a user can call in order to give the Hive things to do. They could call
`do_task` on an individual drone if they really wanted, but that would bypass
all control from the queens, and wouldn't be recomended (a good improvement is
to ensure `do_task` calls only come from the queen). The `submit_task` would look
something like this:

```diff
diff --git a/larve.py b/larve.py
index e0b3fd3..40d5d9f 100644
--- a/larve.py
+++ b/larve.py
@@ -30,6 +30,18 @@ def healthz():
     }
     return jsonify(current_health)

+
+@app.route('/submit_task', methods=['POST'])
+def submit_task():
+    if not request.json or not 'text' in request.json:
+        abort(400)
+    if larve_mode == Mode.DRONE:
+        abort(400, description='In drone mode, not scheduling tasks')
+    task = request.json.get('text')
+    # Send task to a drone...
+    return jsonify({'result': 'OK'})
+
+
 @app.route('/do_task', methods=['POST'])
 def do_task():
     if not request.json or not 'text' in request.json:
```

The implementation is very similar to `do_task` -- we change our check to make
sure we are not in drone mode, we still validate our input, and we return OK.
However, the eagle-eyed reader would notice the comment "Send task to a drone".
For this to happen, the queen needs to know who the drones are. There are two
ways of going about this:

 - The queen goes out and finds the drones
 - The drones tell the queen where they are

The first option starts flirting with the topic of service discovery, so let's
stick with option two. To implement this, we need to add a data structure to our
queen: a list of all the drones and how to contact them: their host and port, and
a way for the drone to register themselves to the queen. We will save this for
part 3, as we also want to take some time to clean up our code and make it
easier to do tasks in parallel with serving the API endpoints.
