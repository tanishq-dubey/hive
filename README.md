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

## Part 3: For Her Majesty's Distributed Service

In this part we want to accomplish three tasks:

 1. Have drones register with queens, and have queens keep a list of drones
 2. Have queeens give a task to a random drone.
 3. Have queens heartbeat with drones


Relatively speaking, this is a pretty tall order for one part, and some parts
will require more extensive changes than others, so we will do this in 3 subsections.

Before we begin, let's discuss what we are trying to accomplish here. First, we want
to be able to have our drones register with the queens so that our queens know who
they can send tasks to. we are doing drone->queen registration as opposed to 
queen->drone because it is simpler. If we did queen->drone we would have to do some
sort of service discovery, which is likely out of the scope of this series of posts,
but may come as an addon post far in the future. Of course, doing drone->queen
registration does have its downsides. For one, it demands that our queen's host:port
does not change, however this is generally solved by putting our queen(s) behind a
static loadbalancer host:port, and letting the individual queens change as much as
they want. We also need to have the queens keep a list of the drones that are available.
For now we will make two assumptions:

 1. The only thing we need to know about a drone is its host:port
 2. There is only one queen

These are important assumptions to make. Firstly, drones can a tons of metadata. In
kubernetes, worker metadata includes things like version, capacity (CPU/memory), name,
kernel version, IP ranges, and so on. We will eventually incorporate things like capacity
once we get to scheduling, but for now, just host:port, so we know where to send commands
will suffice. In additon, the assumption of only one queen is hugely important. If we
have multiple queens, we will need to make sure that all the queens have the same
list of drones: a concensus problem. Kubernetes solves this by using `etcd`, a
distributed key-value store that performns concensus on its data, so everyone sees the
same version of it. If we had multiple queens, we would need to do the same, either
use something like `etcd`, or implement this ourselves. For now we will bypass
this problem, but it will come back around sooner than we think.

The next part will be quite simple, once the queen gets a job on the
`submit_task` endpoint, randomly pick a drone from its list and call `do_task` with the
task information.

Finally we want our queens to heartbeat with our drones. The primary purpose of this, for now,
is to know wheather a drone is available or not. By heartbeating with every drone in
its list, the queen can remove drones that have been unavailable for too long, ensuring
they don't get tasks assigned to them. We also want to setup heartbeating so we can modify
our code to do things in parallel. Heartbeating will be used later on to also keep track
of the work drones are doing, and updating their state in the queen's store.

That was a lot to take in, so let's get to writing some code.


### License and Registration Please

```
drone = dict()
```

inside this dictionary, we can store some really basic info for now, such as the
name of the drone and the host and port:

```
{
    "drone1": "127.0.0.1:5001"
}
```
And if we have multiple:

```
{
    "drone1": "127.0.0.1:5001",
    "drone2": "127.0.0.1:5002"
}
```

Don't worry, we will be adding more metadata later, this is just our basic
implementation. To begin, let's add a `/register` endpoint to the queen, so
drones can inform her of their existence:

```diff
diff --git a/larve.py b/larve.py
index 40d5d9f..9792945 100644
--- a/larve.py
+++ b/larve.py
@@ -20,6 +20,9 @@ larve_status = Status.NOT_READY
 larve_mode   = Mode.DRONE
 larve_verson = '0.0.1'

+# A blank drone list
+drones = dict()
+
 # What to do on '/healthz'
 @app.route('/healthz', methods=['GET'])
 def healthz():
@@ -41,6 +44,16 @@ def submit_task():
     # Send task to a drone...
     return jsonify({'result': 'OK'})

+@app.route('/register', methods=['POST'])
+def register():
+    global drones
+    if not request.json or not 'address' in request.json:
+        abort(400)
+    if larve_mode == Mode.DRONE:
+        abort(400, description='In drone mode, not taking registration')
+    drones[request.json.get('address')] = 'drone-' + str(len(drones))
+    return jsonify({'result': 'OK'})
+

 @app.route('/do_task', methods=['POST'])
 def do_task():
```

Simple enough, right? We create a dictionary of drones, and upon the register endpoint
being called, we add the drone in the following format: `"host:port" : "drone name"`,
for example: `127.0.0.1:5000: "drone-1"`. 

With this done, we need to modify the drone logic such that it registers with the queen
on start up. To do that we will add an additional argument to our Larve so that if the
larve is a drone, it will require an argument for the queen host and port. In additon,
we should add an argument to be able to change the port the Larve runs on, so we don't
have port conflicts when running multiple drones. Let's see these changes:

```diff
diff --git a/larve.py b/larve.py
index 9792945..15b9a07 100644
--- a/larve.py
+++ b/larve.py
@@ -1,7 +1,10 @@
 import argparse
+import sys
+from enum import Enum
+import json

 from flask import Flask, jsonify, request, abort
-from enum import Enum
+import requests

 app = Flask(__name__)

@@ -71,11 +74,22 @@ def do_task():
 if __name__ == '__main__':
     # When we start, set our status
     parser = argparse.ArgumentParser(description='Hive Larve Daemon')
-    parser.add_argument("--queen", dest='queen', action='store_true')
+    parser.add_argument("--queen", dest='queen', action='store_true', help="Start this larve in queen mode")
+    parser.add_argument("--queen-host", dest='queenhost', required='--queen' not in sys.argv, help="If running in drone mode, host and port of the queen to register with, example: 127.0.0.1:8080")
+    parser.add_argument("--port", dest='port', nargs='?', const=1, type=int, default=8080, help="Port to run on, default 8080")
     parser.set_defaults(queen=False)
     args = parser.parse_args()

     if args.queen:
         larve_mode = Mode.QUEEN
+    else:
+        payload = { "address": "127.0.0.1:" + str(args.port) }
+        headers = { 'Content-Type': 'application/json' }
+        resp = requests.request("POST", 'http://' + args.queenhost + '/register', headers=headers, data = json.dumps(payload))
+        if resp.status_code > 299:
+            print("Could not register to queen")
+            sys.exit(-1)
+        print(f"Registered to {args.queenhost}")
+
     larve_status = Status.READY
-    app.run(debug=True)
+    app.run(debug=True, port=args.port)
```

### As you command

Next, we can modify our comment on the queens of sending jobs to drones. For now our
scheduling will just be sending a task to a random drone:

```diff
diff --git a/larve.py b/larve.py
index 15b9a07..f9ae4a6 100644
--- a/larve.py
+++ b/larve.py
@@ -2,6 +2,7 @@ import argparse
 import sys
 from enum import Enum
 import json
+import random

 from flask import Flask, jsonify, request, abort
 import requests
@@ -39,12 +40,18 @@ def healthz():

 @app.route('/submit_task', methods=['POST'])
 def submit_task():
+    global drones
     if not request.json or not 'text' in request.json:
         abort(400)
     if larve_mode == Mode.DRONE:
         abort(400, description='In drone mode, not scheduling tasks')
     task = request.json.get('text')
     # Send task to a drone...
+    drone_host, drone_name = random.choice(list(drones.items()))
+    payload = { "text": task }
+    headers = { 'Content-Type': 'application/json' }
+    requests.request("POST", 'http://' + drone_host + '/do_task', headers=headers, data=json.dumps(payload))
+    print(f"Sent task to {drone_name}")
     return jsonify({'result': 'OK'})

 @app.route('/register', methods=['POST'])
```

Great! We can start our queen and a drones in the following manner:

```shell
python3 larve.py --queen
```
In two seperate terminals:

```shell
python3 larve.py --queen-host 127.0.0.1:8080 --port 5001
```

```shell
python3 larve.py --queen-host 127.0.0.1:8080 --port 5002
```

We can now submit a task to our queen, and see one of our drones get the job:

```shell
curl --location --request POST 'localhost:8080/submit_task' \
--header 'Content-Type: application/json' \
--data-raw '{
	"text": "hello"
}'
```

### Check their vitals...stat

We now have a basic distributed system, but there is one issue, what if a drone drops out, suppose it dies?
The queen should not be sending commands to a drone that is dead. To prevent this from happening, we will
implement heartbeating in the queen.

How this will work is quite simple: once a drone is registered in the queen's dictionary, in a seperate thread,
the queen will go through this list every _n_ seconds and call the `/healthz` endpoint on the drones. If the
drones do not respond in a timely manner in _m_ attempts, the queen will remove them from their registration
list. The first thing we want to do for this implementation is move our webserver to a seperate thread:

```diff
diff --git a/larve.py b/larve.py
index 15b9a07..86ec532 100644
--- a/larve.py
+++ b/larve.py
@@ -2,6 +2,9 @@ import argparse
 import sys
 from enum import Enum
 import json
+import threading
+import time

 from flask import Flask, jsonify, request, abort
 import requests
@@ -25,6 +28,38 @@ larve_verson = '0.0.1'

 # A blank drone list
 drones = dict()
+drones_lock = threading.Lock()
+
+
+def queen_heartbeat():
+    global drones
+    max_retry = 5
+    while True:
+        print("Starting heartbeat")
+        to_remove = []
+        for k,v in drones.items():
+            success = False
+            count = 1
+            while not success and count < max_retry:
+                try:
+                    print(f"checking {k} ({v})")
+                    requests.get(url= 'http://' + k + '/healthz')
+                    success = True
+                    print(f"check-in from {k} ({v})")
+                except Exception:
+                    print(f"could not check {k} ({v}) on attempt {count}/{max_retry}")
+                    count = count + 1
+                    time.sleep(.5)
+            if count >= max_retry:
+                to_remove.append(k)
+                print(f"marking {k} ({v}) for removal from drone list")
+                print(drones)
+
+        for r in to_remove:
+            print(f"removed {r} from drone list")
+            drones.pop(r, None)
+        time.sleep(10)
+

 @app.route('/register', methods=['POST'])
@@ -79,9 +120,13 @@ if __name__ == '__main__':
     parser.add_argument("--port", dest='port', nargs='?', const=1, type=int, default=8080, help="Port to run on, default 8080")
     parser.set_defaults(queen=False)
     args = parser.parse_args()
+    flask_thread = threading.Thread(target=app.run, kwargs={'port': args.port})
+    flask_thread.start()
+    heartbeat_thread = threading.Thread(target=queen_heartbeat)

     if args.queen:
         larve_mode = Mode.QUEEN
+        heartbeat_thread.start()
     else:
         payload = { "address": "127.0.0.1:" + str(args.port) }
         headers = { 'Content-Type': 'application/json' }
@@ -92,4 +137,8 @@ if __name__ == '__main__':
         print(f"Registered to {args.queenhost}")

     larve_status = Status.READY
-    app.run(debug=True, port=args.port)
+
+
+    flask_thread.join()
+    if args.queen:
+        heartbeat_thread.join()
```

We've accomplished a lot in the last code diff. We are now running multiple tasks
in a single program. Specifically, we are running our API server and our heartbeating
method in two threads, so that we can accept tasks and check on our drones -- in the
queens -- at the same time. Looking at our `queen_hearbeat` function, we can see that
it iterates over the entire list of drones and calls the `/healtz` endpoint on
them. If there is a problem reaching the drone, we try again for `max_retry`
times, and if we get multiple failures, we mark the drone for deletion. After this,
we go to sleep and try heartbeating later.

There is one major bug in this implementation. Specifically, if a drone were to register
during a heartbeat, we may or may not catch it. In addition, if we were submitted a
task while drone was registering or being removed, we might not assign it work or 
wrongly assign work to a drone that no longer exists. 

The eagle eyed reader might notice `drones_lock = threading.Lock()` added in the last
diff. We can use this lock to make sure our drone dictionary is not modified while
we are heartbeating, or if we are assigning/registering drones. Let's see how this
changes the final code for this part:

```diff
diff --git a/larve.py b/larve.py
index 86ec532..6ed687a 100644
--- a/larve.py
+++ b/larve.py
@@ -33,9 +33,12 @@ drones_lock = threading.Lock()

 def queen_heartbeat():
     global drones
+    global drones_lock
+
     max_retry = 5
     while True:
         print("Starting heartbeat")
+        drones_lock.acquire()
         to_remove = []
         for k,v in drones.items():
             success = False
@@ -58,44 +61,61 @@ def queen_heartbeat():
         for r in to_remove:
             print(f"removed {r} from drone list")
             drones.pop(r, None)
+
+        drones_lock.release()
         time.sleep(10)


 # What to do on '/healthz'
 @app.route('/healthz', methods=['GET'])
 def healthz():
+    global drones
     current_health = {
         "status": str(larve_status),
         "version": larve_verson,
         "mode": str(larve_mode)
     }
+
+    if larve_mode == Mode.QUEEN:
+        current_health['drones'] = drones
+
     return jsonify(current_health)


 @app.route('/submit_task', methods=['POST'])
 def submit_task():
     global drones
+    global drones_lock
     if not request.json or not 'text' in request.json:
         abort(400)
     if larve_mode == Mode.DRONE:
         abort(400, description='In drone mode, not scheduling tasks')
     task = request.json.get('text')
+
     # Send task to a drone...
+    drones_lock.acquire()
     drone_host, drone_name = random.choice(list(drones.items()))
     payload = { "text": task }
     headers = { 'Content-Type': 'application/json' }
     requests.request("POST", 'http://' + drone_host + '/do_task', headers=headers, data=json.dumps(payload))
     print(f"Sent task to {drone_name}")
+    drones_lock.release()
+
     return jsonify({'result': 'OK'})

 @app.route('/register', methods=['POST'])
 def register():
     global drones
+    global drones_lock
     if not request.json or not 'address' in request.json:
         abort(400)
     if larve_mode == Mode.DRONE:
         abort(400, description='In drone mode, not taking registration')
+
+    drones_lock.acquire()
     drones[request.json.get('address')] = 'drone-' + str(len(drones))
+    drones_lock.release()
+
     return jsonify({'result': 'OK'})

```

Adding these locks ensure that while we are doing work the data we are handling
will not change. We also added a drones list to the queen `healthz` endpoint,
just for debugging.

We can test all of these changes rather quickly. If we follow the
same queen and two drone startup procedure, we will see that we are heartbeating
will all the drones, and at the same time we can ask the queen drone for 
its health.  We can also shut down a drone, and watch as the heartbeating removes
the "unhealthy" drone from the queen's list. Finally, we if add another drone,
remove it, and submit a task while the removal heartbeating is occuring, we will
notice a delay in the server responding to us, ensuring the locking is working.

Part 4 will be a short one, we will clean up the code and add proper logging.
All this will prepare us for part 5, which will fix an even bigger problem in
our system: what happens when the queen dies? For this we will need multiple
queen, and some sort of concensus between them...