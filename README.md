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
our API, rather something more efficient like Protobuf.

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
to become one of two things: a drone, the worker unit, or a queen, the commanding
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
be a queen ordering the drone to do something. With this in mind, we can declare that
the simplest Hive would consist of one queen and one drone. The user would interface
with the queen to provide tasks, and the queen would hand those tasks to the drone.
Do note that the queen is not doing any work here. All the queen is responsible for is
maintaining the state of the Hive, and like in stereotypical royal fashion, not doing
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
all control from the queens, and wouldn't be recommended (a good improvement is
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
 2. Have queens give a task to a random drone.
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
static load-balancer host:port, and letting the individual queens change as much as
they want. We also need to have the queens keep a list of the drones that are available.
For now we will make two assumptions:

 1. The only thing we need to know about a drone is its host:port
 2. There is only one queen

These are important assumptions to make. Firstly, drones can a tons of metadata. In
kubernetes, worker metadata includes things like version, capacity (CPU/memory), name,
kernel version, IP ranges, and so on. We will eventually incorporate things like capacity
once we get to scheduling, but for now, just host:port, so we know where to send commands
will suffice. In addition, the assumption of only one queen is hugely important. If we
have multiple queens, we will need to make sure that all the queens have the same
list of drones: a consensus problem. Kubernetes solves this by using `etcd`, a
distributed key-value store that performs consensus on its data, so everyone sees the
same version of it. If we had multiple queens, we would need to do the same, either
use something like `etcd`, or implement this ourselves. For now we will bypass
this problem, but it will come back around sooner than we think.

The next part will be quite simple, once the queen gets a job on the
`submit_task` endpoint, randomly pick a drone from its list and call `do_task` with the
task information.

Finally we want our queens to heartbeat with our drones. The primary purpose of this, for now,
is to know whether a drone is available or not. By heartbeating with every drone in
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
larve is a drone, it will require an argument for the queen host and port. In addition,
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

How this will work is quite simple: once a drone is registered in the queen's dictionary, in a separate thread,
the queen will go through this list every _n_ seconds and call the `/healthz` endpoint on the drones. If the
drones do not respond in a timely manner in _m_ attempts, the queen will remove them from their registration
list. The first thing we want to do for this implementation is move our webserver to a separate thread:

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
queens -- at the same time. Looking at our `queen_heartbeat` function, we can see that
it iterates over the entire list of drones and calls the `/healthz` endpoint on
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
queen, and some sort of consensus between them...

## Part 4: Good Will Cleaning

This part is very subjective because it is about code cleanup and organization.
There are two major goals we want to accomplish:
 1. Organize our code so that future additions are easy
 2. Add logging, so it is clear what is going on when we run

Since a lot of the diffs here won't really help, the best course of action is 
to post two code blocks: our current state, and a cleaned state, which we will
use starting in part 5. So without further ado:

### The Current State of the Sode
```python
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
```

### Post Cleanup And Logging

```python
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

```

Some stuff has changed. Specifically, we have run the code though the `yapf`
formatter, just to get a bit of standardized cleanup. We've also implemented
structured logging, which is our route of going about our log cleanup. Finally
we've used `gevent` with monkey patching to cleanup how we start the Flask
API server and and cleanup Flask logging. There are other minor changes, a
full read of the cleaned up code is recommended.

All this done, we are finally ready to dive into getting multiple queens
up and running and making sure our cluster is able to survive a failure
in a queen.


## Part 5: Castaway

In what will probably be the longest part of our tutorial, we will begin to
discuss and implement consensus. Now, consensus is  hard problem, so we
won't be coming up with our own algorithm to do this. Instead, we will be
using Raft, a well known distributed consensus algorithm.

In addition to this, we won't first learn about Raft, and then go implement
it, that takes far too long and is quite boring. Instead, we will build Raft
and learn it at the same time. By the end of part 5, we will have created a
distributed key-value store that the queens can use to communicate with each
other and keep track of nodes, so we can handle _floor(n/2)_ failures. Let's get
to it.

### Follow the leader.

Raft relies on a leader node, or one of the members of the Raft group to be in
charge. This is the person that does all the work while they are leader and 
informs everyone else of the work that has been done. In our case, this is
basically the "queen of queens". Of course, if we have multiple queens, who
gets to be the leader? For this, we start by doing leader election. That is,
the queen will decide amongst themselves who is the leader.

In order to do this, Raft has 3 states:
 - Follower
 - Candidate
 - Leader

A follower is someone that follows the leader. A candidate is someone that has
the potential to be a lader, this is only during the election phase. And a leader,
is of course a leader. On init, everyone is a follower, let's write that:

```diff
diff --git a/larve.py b/larve.py
index 7ea9da0..db88549 100644
--- a/larve.py
+++ b/larve.py
@@ -36,6 +36,13 @@ class Mode(Enum):
     QUEEN = 2


+# A member of a Raft group can be in one of three states
+# Everyone starts in the follower state
+class RaftState(Enum):
+    FOLLOWER = 1
+    CANDIDATE = 2
+    LEADER = 3
+
 # Create the Flask API server
 app = Flask(__name__)

@@ -46,6 +53,7 @@ log = structlog.get_logger()
 larve_status = Status.NOT_READY
 larve_mode = Mode.DRONE
 larve_verson = '0.0.1'
+raft_state = RaftState.FOLLOWER

 # A blank drone list
 drones = dict()
@@ -104,8 +112,10 @@ def healthz():
     }

     # If we are a queen, show the drones we know about
+    # We also care about the raft state
     if larve_mode == Mode.QUEEN:
         current_health['drones'] = drones
+        current_health['raft_state'] = str(raft_state)

     return jsonify(current_health)

```

Cool, so upon queen startup, we can see on `healthz`

```json
{
    "drones": {},
    "mode": "Mode.QUEEN",
    "raft_state": "RaftState.FOLLOWER",
    "status": "Status.READY",
    "version": "0.0.1"
}
```

Of course, being a follower is boring when there is no leader around, so if we
don't hear from a leader node in a while, we can try and become a candidate.
This sounds like we would need a thread to handle all of our raft stuff, so let's
add that and also add a `last_heartbeat` variable, so we can keep track of heart
beat times. This is necessary because hearing from a leader is basically the same as
the queens heartbeating amongst each other.

```diff
diff --git a/larve.py b/larve.py
old mode 100644
new mode 100755
index 7ea9da0..3b95b5a
--- a/larve.py
+++ b/larve.py
     FOLLOWER = 1
     CANDIDATE = 2
     LEADER = 3
 
 
+# The unix time (in seconds) we last heard from someone
+last_heartbeat = int(time.time())
+
+
 # Create the Flask API server
 app = Flask(__name__)

@@ -46,6 +58,10 @@ log = structlog.get_logger()
 larve_status = Status.NOT_READY
 larve_mode = Mode.DRONE
 larve_verson = '0.0.1'
 raft_state = RaftState.FOLLOWER

+# Our leader timeout is anywhere between 5 and 15 seconds
+raft_leader_timeout = random.randint(5, 15)

 # A blank drone list
 drones = dict()
@@ -93,19 +109,38 @@ def queen_heartbeat():
         time.sleep(10)


+def raft():
+    global raft_state
+    while True:
+        if raft_state == RaftState.FOLLOWER:
+            if (int(time.time()) - last_heartbeat) > raft_leader_timeout:
+                raft_state = RaftState.CANDIDATE
+                log.info("Changing raft state", previous=str(RaftState.FOLLOWER), next=str(RaftState.CANDIDATE))
+            else:
+                time.sleep(1)
+
+
 # What to do on '/healthz'
 @app.route('/healthz', methods=['GET'])
 def healthz():
     global drones
+    global last_heartbeat
+
+    last_heartbeat = int(time.time())
+
     current_health = {
         "status": str(larve_status),
         "version": larve_verson,
-        "mode": str(larve_mode)
+        "mode": str(larve_mode),
+        "last_heartbeat": last_heartbeat
     }

     # If we are a queen, show the drones we know about


@@ -258,10 +293,19 @@ if __name__ == "__main__":
     log.info("started thread", name="api-server")

     if args.queen:
+        # Start building a raft with other queens
+        raft_state = RaftState.FOLLOWER
+        raft_thread = threading.Thread(target=raft)
+
         # Start queen heartbeating
         larve_mode = Mode.QUEEN
         heartbeat_thread = threading.Thread(target=queen_heartbeat)
+
+        raft_thread.start()
         heartbeat_thread.start()
+
+        thread_list.append(raft_thread)
+        log.info("started thread", name="raft", timeout=raft_leader_timeout)
         thread_list.append(heartbeat_thread)
         log.info("started thread", name="queen-heartbeat")
     else:
```

Now if we start up a queen, and don't visit `healthz`, we will get logs like this:

```
➜  hive git:(master) ./larve.py --queen
2020-05-29 01:00.59 started thread                 name=api-server
2020-05-29 01:00.59 starting task                  task=heartbeat
2020-05-29 01:00.59 completed task                 task=heartbeat
2020-05-29 01:00.59 started thread                 name=raft timeout=6
2020-05-29 01:00.59 started thread                 name=queen-heartbeat
2020-05-29 01:01.06 Changing raft state            next=RaftState.CANDIDATE previous=RaftState.FOLLOWER
```

Getting even further! Now that we are in a candidate state, what do we want to
do? Well, candidates, even in real life, go out and collect votes from everyone
else, so we want our queens to do the same. This should give some intuition as 
to why we chose a random amount of time for our leader timeout. By doing this,
we can try and ensure that one queen will become candidate first, and by making
it random, and not based on something static, such as port number, we can ensure
it isn't always the same queen.

Before we get to the implementation of getting votes, let's add a helper script
that will start 5 queens for us, `start_queens.sh`

```shell
#!/bin/bash

xpanes -sstc "./larve.py --queen --port {}" {8080..8084}
```

This utilizes `tmux` and the fantastic [`xpanes`](https://github.com/greymd/tmux-xpanes)
tool. Making our life easier.

Let's get to collecting votes. We want to add an endpoint `request_vote` and
a function to send a request as well. While we are sending the request, we come
up with a interesting question: who are the other queens? We will take the simplest
route here, and provide, to each queen, a list of all the other queens, so our startup
command would look something like this:

```shell
./larve.py --queen --port 8080 --queen-list localhost:8081,localhost:8082...
```

The changes look like this:

```diff
diff --git a/larve.py b/larve.py
index 3b95b5a..a9cd4bb 100755
--- a/larve.py
+++ b/larve.py
@@ -15,6 +15,7 @@ import struct
 import sys
 import threading
 import time
+import math

 from enum import Enum

@@ -59,14 +60,18 @@ larve_status = Status.NOT_READY
 larve_mode = Mode.DRONE
 larve_verson = '0.0.1'
 raft_state = RaftState.FOLLOWER
+interface = ""

 # Our leader timeout is anywhere between 5 and 15 seconds
-raft_leader_timeout = random.randint(5, 15)
+raft_election_timeout = random.randint(5, 15)

 # A blank drone list
 drones = dict()
 drones_lock = threading.Lock()

+# A blank queen list
+queens = []
+

 # Function for the heartbeat thread
 def queen_heartbeat():
@@ -76,49 +81,94 @@ def queen_heartbeat():
     max_retry = 5
     # We always want to be heartbeating
     while True:
-        log.info("starting task", task="heartbeat")
-        drones_lock.acquire()
-        to_remove = []
-        for k, v in drones.items():
-            success = False
-            count = 1
-            while not success and count < max_retry:
-                try:
-                    log.info("heartbeating with drone", host=k, name=v)
-                    requests.get(url='http://' + k + '/healthz')
-                    success = True
-                    log.info("got heartbeat with drone", host=k, name=v)
-                except Exception:
-                    log.warning("could not reach drone",
-                                host=k,
-                                name=v,
-                                attempt=count,
-                                max_attempt=max_retry)
-                    count = count + 1
-                    time.sleep(.5)
-            if count >= max_retry:
-                to_remove.append(k)
-                log.warning("marking drone for removal", host=k, name=v)
-
-        for r in to_remove:
-            log.warning("removed drone from list", host=r)
-            drones.pop(r, None)
-
-        drones_lock.release()
-        log.info("completed task", task="heartbeat")
+        if raft_state == RaftState.LEADER:
+            log.info("starting task", task="drone heartbeat")
+            drones_lock.acquire()
+            to_remove = []
+            for k, v in drones.items():
+                success = False
+                count = 1
+                while not success and count < max_retry:
+                    try:
+                        log.info("heartbeating with drone", host=k, name=v)
+                        requests.get(url='http://' + k + '/healthz')
+                        success = True
+                        log.info("got heartbeat with drone", host=k, name=v)
+                    except Exception:
+                        log.warning("could not reach drone",
+                                    host=k,
+                                    name=v,
+                                    attempt=count,
+                                    max_attempt=max_retry)
+                        count = count + 1
+                        time.sleep(.5)
+                if count >= max_retry:
+                    to_remove.append(k)
+                    log.warning("marking drone for removal", host=k, name=v)
+
+            for r in to_remove:
+                log.warning("removed drone from list", host=r)
+                drones.pop(r, None)
+
+            drones_lock.release()
+            log.info("completed task", task="drone heartbeat")
         time.sleep(10)


 def raft():
     global raft_state
+
+    # We're always doing raft
     while True:
+
         if raft_state == RaftState.FOLLOWER:
-            if (int(time.time()) - last_heartbeat) > raft_leader_timeout:
+            if (int(time.time()) - last_heartbeat) > raft_election_timeout:
                 raft_state = RaftState.CANDIDATE
                 log.info("Changing raft state", previous=str(RaftState.FOLLOWER), next=str(RaftState.CANDIDATE))
             else:
                 time.sleep(1)

+        if raft_state == RaftState.CANDIDATE:
+            log.info("starting vote pool")
+            num_votes = sum(do_list_threaded(send_vote_request_thread, queens))
+            log.info("got votes", count = num_votes, needed=int(math.ceil(len(queens)/2.0)))
+            # Check to see if we have a majority of votes
+            if num_votes > int(math.ceil(len(queens)/2.0)):
+                log.info("Changing raft state", previous=str(RaftState.CANDIDATE), next=str(RaftState.LEADER))
+                raft_state = RaftState.LEADER
+
+        if raft_state == RaftState.LEADER:
+            log.info("doing raft task", task="leader heartbeat")
+            do_list_threaded(send_heartbeat_thread, queens)
+            log.info("completed raft task", task="leader heartbeat")
+            time.sleep(3)
+
+
+def do_list_threaded(func, to_do):
+    ret_list = [0] * len(to_do)
+    do_thread_list = []
+    for i in range(len(to_do)):
+        t = threading.Thread(target=func, args=[to_do[i], i, ret_list])
+        t.start()
+        do_thread_list.append(t)
+
+    for t in do_thread_list:
+        t.join()
+
+    return ret_list
+
+
+def send_heartbeat_thread(host, idx, ret_list):
+    send_heartbeat(host)
+
+
+def send_heartbeat(host):
+    try:
+        requests.get(url='http://' + host + '/healthz')
+    except Exception:
+        log.warning("could not reach larve to heartbeat",
+                    host=host)
+

 # What to do on '/healthz'
 @app.route('/healthz', methods=['GET'])
@@ -145,6 +195,58 @@ def healthz():
     return jsonify(current_health)


+def send_vote_request_thread(voter_queen, idx, ret_list):
+    val = send_vote_request(voter_queen)
+    ret_list[idx] = val
+
+
+def send_vote_request(voter_queen):
+    log.info("sending vote request", queen=voter_queen)
+    self_ip = get_ip_of_interface(interface)
+    payload = {"candidate": self_ip + ":" + str(args.port)}
+    headers = {'Content-Type': 'application/json'}
+
+    try:
+        resp = requests.post('http://' + voter_queen + '/request_vote',
+                             headers=headers,
+                             data=json.dumps(payload))
+    except Exception as e:
+        log.error("could request vote with queen",
+                  queen=voter_queen,
+                  error=e)
+        return 0
+
+    if resp.status_code > 399:
+        log.error("could request vote with queen",
+                  queen=voter_queen,
+                  response=resp.text,
+                  code=resp.status_code)
+        return 0
+
+    if resp.status_code > 299:
+        log.info("queen rejected vote",
+                 queen=voter_queen)
+        return 0
+
+    log.info("got vote from queen", queen=voter_queen)
+
+    return 1
+
+
+@app.route('/request_vote', methods=['POST'])
+def request_vote():
+    global last_heartbeat
+
+    last_heartbeat = int(time.time())
+
+    if not request.json or not 'candidate' in request.json:
+        abort(400)
+
+    log.info("got request for vote", candidate=request.json.get('candidate'))
+
+    return jsonify({'result': 'OK'})
+
+
 # Submit a task to the queen to be assigned to a drone
 @app.route('/submit_task', methods=['POST'])
 def submit_task():
@@ -264,12 +366,20 @@ if __name__ == "__main__":
         help=
         "If running in drone mode, host and port of the queen to register with, example: 127.0.0.1:8080"
     )
+    parser.add_argument(
+        "--queen-list",
+        dest="queenlist",
+        nargs='+',
+        required='--queen' in sys.argv,
+        help=
+        "If running in queen mode, list of all the queens, example: 127.0.0.1:8081 127.0.0.1:8082..."
+    )
     parser.add_argument(
         "--interface",
         dest="net_interface",
-        required='--queen' not in sys.argv,
+        required=True,
         help=
-        "If running in drone mode, network interface the drone should use, example: enp5s0"
+        "Network interface the larve should use, example: enp5s0"
     )
     parser.add_argument("--port",
                         dest="port",
@@ -285,14 +395,19 @@ if __name__ == "__main__":
     if args.queen:
         larve_mode = Mode.QUEEN

+    interface = args.net_interface
+
     # Start APi server
     http_server = WSGIServer(('', args.port), app, log=None)
     http_thread = threading.Thread(target=http_server.serve_forever)
     http_thread.start()
     thread_list.append(http_thread)
-    log.info("started thread", name="api-server")
+    log.info("started thread", name="api-server", port=args.port)

     if args.queen:
+        queens = args.queenlist
+        log.info("in queen mode", queen_list=queens)
+
         # Start building a raft with other queens
         raft_state = RaftState.FOLLOWER
         raft_thread = threading.Thread(target=raft)
@@ -305,7 +420,7 @@ if __name__ == "__main__":
         heartbeat_thread.start()

         thread_list.append(raft_thread)
-        log.info("started thread", name="raft", timeout=raft_leader_timeout)
+        log.info("started thread", name="raft", election_timeout=raft_election_timeout)
         thread_list.append(heartbeat_thread)
         log.info("started thread", name="queen-heartbeat")
     else:

```

Oooooookkkk. That is a lot of changes, but they aren't as bad as they seem.
Let's take a look at them in logical chunks.

```diff
@@ -15,6 +15,7 @@ import struct
 import sys
 import threading
 import time
+import math

 from enum import Enum

@@ -59,14 +60,18 @@ larve_status = Status.NOT_READY
 larve_mode = Mode.DRONE
 larve_verson = '0.0.1'
 raft_state = RaftState.FOLLOWER
+interface = ""

 # Our leader timeout is anywhere between 5 and 15 seconds
-raft_leader_timeout = random.randint(5, 15)
+raft_election_timeout = random.randint(5, 15)

 # A blank drone list
 drones = dict()
 drones_lock = threading.Lock()

+# A blank queen list
+queens = []
+

@@ -264,12 +366,20 @@ if __name__ == "__main__":
         help=
         "If running in drone mode, host and port of the queen to register with, example: 127.0.0.1:8080"
     )
+    parser.add_argument(
+        "--queen-list",
+        dest="queenlist",
+        nargs='+',
+        required='--queen' in sys.argv,
+        help=
+        "If running in queen mode, list of all the queens, example: 127.0.0.1:8081 127.0.0.1:8082..."
+    )
     parser.add_argument(
         "--interface",
         dest="net_interface",
-        required='--queen' not in sys.argv,
+        required=True,
         help=
-        "If running in drone mode, network interface the drone should use, example: enp5s0"
+        "Network interface the larve should use, example: enp5s0"
     )
     parser.add_argument("--port",
                         dest="port",
@@ -285,14 +395,19 @@ if __name__ == "__main__":
     if args.queen:
         larve_mode = Mode.QUEEN

+    interface = args.net_interface
+
     # Start APi server
     http_server = WSGIServer(('', args.port), app, log=None)
     http_thread = threading.Thread(target=http_server.serve_forever)
     http_thread.start()
     thread_list.append(http_thread)
-    log.info("started thread", name="api-server")
+    log.info("started thread", name="api-server", port=args.port)

     if args.queen:
+        queens = args.queenlist
+        log.info("in queen mode", queen_list=queens)
+
         # Start building a raft with other queens
         raft_state = RaftState.FOLLOWER
         raft_thread = threading.Thread(target=raft)
@@ -305,7 +420,7 @@ if __name__ == "__main__":
         heartbeat_thread.start()

         thread_list.append(raft_thread)
-        log.info("started thread", name="raft", timeout=raft_leader_timeout)
+        log.info("started thread", name="raft", election_timeout=raft_election_timeout)
         thread_list.append(heartbeat_thread)
         log.info("started thread", name="queen-heartbeat")
     else:

```
So here, we are modifying our program's entry point. First we are adding the
argument for our queen list and we are making the `interface` required for
queens as well. We've also changed the name of the variable `raft_leader_timeout`
to be `raft_election_timeout`, to match the terminology used in raft papers more.
Finally, we made a couple global variables and added the `math` library. So far, so
simple. Next lets look at how we request votes:

```diff
@@ -145,6 +195,58 @@ def healthz():
     return jsonify(current_health)


+def send_vote_request_thread(voter_queen, idx, ret_list):
+    val = send_vote_request(voter_queen)
+    ret_list[idx] = val
+
+
+def send_vote_request(voter_queen):
+    log.info("sending vote request", queen=voter_queen)
+    self_ip = get_ip_of_interface(interface)
+    payload = {"candidate": self_ip + ":" + str(args.port)}
+    headers = {'Content-Type': 'application/json'}
+
+    try:
+        resp = requests.post('http://' + voter_queen + '/request_vote',
+                             headers=headers,
+                             data=json.dumps(payload))
+    except Exception as e:
+        log.error("could request vote with queen",
+                  queen=voter_queen,
+                  error=e)
+        return 0
+
+    if resp.status_code > 399:
+        log.error("could request vote with queen",
+                  queen=voter_queen,
+                  response=resp.text,
+                  code=resp.status_code)
+        return 0
+
+    if resp.status_code > 299:
+        log.info("queen rejected vote",
+                 queen=voter_queen)
+        return 0
+
+    log.info("got vote from queen", queen=voter_queen)
+
+    return 1
+
+
+@app.route('/request_vote', methods=['POST'])
+def request_vote():
+    global last_heartbeat
+
+    last_heartbeat = int(time.time())
+
+    if not request.json or not 'candidate' in request.json:
+        abort(400)
+
+    log.info("got request for vote", candidate=request.json.get('candidate'))
+
+    return jsonify({'result': 'OK'})
+
+
```

Here we've added the `/request_vote` endpoint that a candidate can call to request
a vote. We've also added a function `send_vote_request`, which a candidate can use
to get a vote from another queen. Just like our other `send` functions, `send_vote_request`
just does a `POST` on the `/request_vote`, but it returns a value based on what the
result of the `POST`. Simply put, if there is anything except a successful call, 
return 0, otherwise return 1. Finally, we have a `send_vote_request_thread` function which
is just a wrapper around our `send_vote_request` function with some extra arguments. We will
get into why that exists later.


```diff
+def send_heartbeat_thread(host, idx, ret_list):
+    send_heartbeat(host)
+
+
+def send_heartbeat(host):
+    try:
+        requests.get(url='http://' + host + '/healthz')
+    except Exception:
+        log.warning("could not reach larve to heartbeat",
+                    host=host)
+
```

We've also done the same for sending heartbeats, here we don't return any values. We also
have a very similar `_thread` function for heartbeating. so what are these thread functions?
To understand this, let's look at their caller function:

```diff
+def do_list_threaded(func, to_do):
+    ret_list = [0] * len(to_do)
+    do_thread_list = []
+    for i in range(len(to_do)):
+        t = threading.Thread(target=func, args=[to_do[i], i, ret_list])
+        t.start()
+        do_thread_list.append(t)
+
+    for t in do_thread_list:
+        t.join()
+
+    return ret_list
+
+
```

This `do_list_threaded` function is essentially a threaded `map` implementation. Now, I realize
that python has things like `multiprocessing.Pool` with a `map` implementation, but this provides
a nice learning opportunity and makes the implementation relatively language agnostic. What we are
doing here is passing `do_list_threaded` a function and a list. For every item in the `to_do` list,
we call the function, `func` with the item in a thread and start it. Then, we join the threads back.
Now, to collect the results, we have a list we create initialized to 0 with the same length as the
`to_do` list. So when we start a threaded task, we pass it the list and the index of the list it 
should write to. If you look at the implementation of the `send_vote_request_thread` function, you'll
see this in action.

> Now, I do know that with Python's GIL and us sharing a list, there will be lots of locking and very little threading
> however, since this tutorial is supposed to be relatively language agnostic, this implementation gives the right
> idea of what should be happening, and that's what matters in the end.

So that's all the extra functions we added, now what did we do the Raft portion?

```diff
 def raft():
     global raft_state
+
+    # We're always doing raft
     while True:
+
         if raft_state == RaftState.FOLLOWER:
-            if (int(time.time()) - last_heartbeat) > raft_leader_timeout:
+            if (int(time.time()) - last_heartbeat) > raft_election_timeout:
                 raft_state = RaftState.CANDIDATE
                 log.info("Changing raft state", previous=str(RaftState.FOLLOWER), next=str(RaftState.CANDIDATE))
             else:
                 time.sleep(1)

+        if raft_state == RaftState.CANDIDATE:
+            log.info("starting vote pool")
+            num_votes = sum(do_list_threaded(send_vote_request_thread, queens))
+            log.info("got votes", count = num_votes, needed=int(math.ceil(len(queens)/2.0)))
+            # Check to see if we have a majority of votes
+            if num_votes > int(math.ceil(len(queens)/2.0)):
+                log.info("Changing raft state", previous=str(RaftState.CANDIDATE), next=str(RaftState.LEADER))
+                raft_state = RaftState.LEADER
+
+        if raft_state == RaftState.LEADER:
+            log.info("doing raft task", task="leader heartbeat")
+            do_list_threaded(send_heartbeat_thread, queens)
+            log.info("completed raft task", task="leader heartbeat")
+            time.sleep(3)
+
```

Wow, lots of changes, but more exciting, things to do when we are a candidate and a leader!
Our first change is, of course, the change of `raft_leader_timeout` to `raft_election_timeout`.
Next, we have things to do when we are a candidate. First off, we can see that as soon as
we become a candidate, we begin to collect votes using our `do_list_threaded` function. We 
pass this our `send_vote_request_thread` as the function to map on and the list of queens as
the things to map. We then take the resultant list and find the sum of that. The reason we
do this is because if a queen voted for us, we return a 1, so to found out how many votes we 
got, all we need to do is sum our votes array. 

Next, in Raft, we can tell if we won a election
simply by seeing if we got a majority of the votes, so even if some queens didn't respond to our
election, so long as a majority did we can declare ourself as leader. 

If we did receive a majority
of the votes, then we make the transition to the leader state. In the leader state, we don't do much
yet, we simply send heartbeats to the queens using the same `do_list_threaded` and the `send_heartbeat_thread`
function.

Our final change is this:

```diff
@@ -76,49 +81,94 @@ def queen_heartbeat():
     max_retry = 5
     # We always want to be heartbeating
     while True:
-        log.info("starting task", task="heartbeat")
-        drones_lock.acquire()
-        to_remove = []
-        for k, v in drones.items():
-            success = False
-            count = 1
-            while not success and count < max_retry:
-                try:
-                    log.info("heartbeating with drone", host=k, name=v)
-                    requests.get(url='http://' + k + '/healthz')
-                    success = True
-                    log.info("got heartbeat with drone", host=k, name=v)
-                except Exception:
-                    log.warning("could not reach drone",
-                                host=k,
-                                name=v,
-                                attempt=count,
-                                max_attempt=max_retry)
-                    count = count + 1
-                    time.sleep(.5)
-            if count >= max_retry:
-                to_remove.append(k)
-                log.warning("marking drone for removal", host=k, name=v)
-
-        for r in to_remove:
-            log.warning("removed drone from list", host=r)
-            drones.pop(r, None)
-
-        drones_lock.release()
-        log.info("completed task", task="heartbeat")
+        if raft_state == RaftState.LEADER:
+            log.info("starting task", task="drone heartbeat")
+            drones_lock.acquire()
+            to_remove = []
+            for k, v in drones.items():
+                success = False
+                count = 1
+                while not success and count < max_retry:
+                    try:
+                        log.info("heartbeating with drone", host=k, name=v)
+                        requests.get(url='http://' + k + '/healthz')
+                        success = True
+                        log.info("got heartbeat with drone", host=k, name=v)
+                    except Exception:
+                        log.warning("could not reach drone",
+                                    host=k,
+                                    name=v,
+                                    attempt=count,
+                                    max_attempt=max_retry)
+                        count = count + 1
+                        time.sleep(.5)
+                if count >= max_retry:
+                    to_remove.append(k)
+                    log.warning("marking drone for removal", host=k, name=v)
+
+            for r in to_remove:
+                log.warning("removed drone from list", host=r)
+                drones.pop(r, None)
+
+            drones_lock.release()
+            log.info("completed task", task="drone heartbeat")
         time.sleep(10)
```

Now, not much really happened here, we just added the if statement:

```diff
+        if raft_state == RaftState.LEADER:
```

And indented the rest of the code to be within it. This just means
only the leader queen heartbeats with the drones. 

This was primarily added for a cool experiment we can do. 
If we start up multiple queens, we can see
the leader election happen and the leader queen begin heartbeating. Because on
every heartbeat we reset the `raft_election_timeout` the other queens remain in
follower mode. If we then kill the leader queen, we will notice one of the other 
queens will initiate a election and become the leader. At that point it will
take over the duty of heartbeating with the drones. A failure resilient system (or
at least, somewhat resilient)!

Finally, we did have some other diffs in terms of tooling. We changed our `start_queens.sh`
to look like this:

```diff
diff --git a/start_queens.sh b/start_queens.sh
index ad5b01e..33490d0 100755
--- a/start_queens.sh
+++ b/start_queens.sh
@@ -1,3 +1,3 @@
 #!/bin/bash

-xpanes -sstc "./larve.py --queen --port {}" {8080..8084}
+xpanes -sstc "python3 ./start_queens.py {} 8080 8084" {8080..8084}
```

You can see we now call a `start_queens.py` script. Since we need to pass in a list
of all the other queens when we start up, using a script is a easy way to do this. The
`start_queens.py` looks like this:


```python
import sys
import subprocess

port = sys.argv[1]
min_port = sys.argv[2]
max_port = sys.argv[3]

ports = list(range(int(min_port), int(max_port) + 1))
ports.remove(int(port))

port_string = ""
host = '127.0.0.1'

for p in ports:
    port_string = port_string + f"{host}:{p} "

subprocess.run(f'./larve.py --queen --interface enp5s0 --queen-list {port_string} --port {port}', check=True, shell=True)

```

Nothing crazy here. Since this is simple tooling, I won't go through trying to use
`argparse` or explaining it. But feel free to create a issue if you have any questions!

That is enough for this commit, we will continue part 5 in the next sub section, where
we fix a bug in our implementation: split brain, or what happens when 2 leaders 
both win the election.

### Dr. Jekyll and Mr. Hyde

Suppose we start up in a particular scenario where two of our queens have the
same or similar election timeouts and so become candidates at basically the same
time, what would happen in this case? Well, in our current implementation:
  - Both candidate queens would send out vote requests to the other queens
  - The other follower queens would reply successfully (the only error conditions are
  if we don't have the correct body or if are down)
  - Both candidate queens get a "majority" of replies and so assume they are the leader
  - We now have two leaders

Uh-oh. 

Two leaders is bad for our cluster because it means that each leader queen can say that
they are right and overwrite the other leader queen, even if they have bad data! So how
do we fix this? Well we can incorporate some things we have in leader elections in the
real world, such as when we vote for someone running for a government position.

When we vote in the real world, we -- generally speaking -- only vote for one candidate,
so we should do the same here. However, there is one nuance to this rule. When we vote
for government office, we vote for one person _per term_, otherwise (in the strictest 
definition of the election rules) we could vote for one person whenever we want. Since
computers are sticklers for rules, we should also implement terms for our elections.

Here's how we do this:

```diff
diff --git a/larve.py b/larve.py
index df5e705..87c0676 100755
--- a/larve.py
+++ b/larve.py
@@ -21,7 +21,7 @@ from enum import Enum

 import requests
 import structlog
-from flask import Flask, jsonify, request, abort
+from flask import Flask, jsonify, request, abort, Response
 from gevent.pywsgi import WSGIServer


@@ -59,11 +59,13 @@ log = structlog.get_logger()
 larve_status = Status.NOT_READY
 larve_mode = Mode.DRONE
 larve_verson = '0.0.1'
-raft_state = RaftState.FOLLOWER
 interface = ""

 # Our leader timeout is anywhere between 5 and 15 seconds
 raft_election_timeout = random.randint(5, 15)
+raft_state = RaftState.FOLLOWER
+raft_term = 0
+raft_lock = threading.Lock()

 # A blank drone list
 drones = dict()
@@ -117,6 +119,9 @@ def queen_heartbeat():

 def raft():
     global raft_state
+    global raft_term
+    global raft_lock
+    global last_heartbeat

     # We're always doing raft
     while True:
@@ -130,13 +135,22 @@ def raft():

         if raft_state == RaftState.CANDIDATE:
             log.info("starting vote pool")
+            raft_lock.acquire()
+            raft_term = raft_term + 1
+            raft_lock.release()
             num_votes = sum(do_list_threaded(send_vote_request_thread, queens))
-            log.info("got votes", count = num_votes, needed=int(math.ceil(len(queens)/2.0)))
+            # Vote for ourselves
+            num_votes = num_votes + 1
+            last_heartbeat = int(time.time())
+            votes_needed = int(math.ceil((len(queens) + 1)/2.0))
+            log.info("got votes", count = num_votes, needed=votes_needed, term=raft_term)
             # Check to see if we have a majority of votes
-            if num_votes > int(math.ceil(len(queens)/2.0)):
+            if num_votes > votes_needed:
                 log.info("Changing raft state", previous=str(RaftState.CANDIDATE), next=str(RaftState.LEADER))
                 raft_state = RaftState.LEADER
-
+            else:
+                log.info("Changing raft state", previous=str(RaftState.CANDIDATE), next=str(RaftState.FOLLOWER))
+                raft_state = RaftState.FOLLOWER
         if raft_state == RaftState.LEADER:
             log.info("doing raft task", task="leader heartbeat")
             do_list_threaded(send_heartbeat_thread, queens)
@@ -201,9 +215,14 @@ def send_vote_request_thread(voter_queen, idx, ret_list):


 def send_vote_request(voter_queen):
-    log.info("sending vote request", queen=voter_queen)
+    global raft_term
+
+    log.info("sending vote request", queen=voter_queen, term=raft_term)
     self_ip = get_ip_of_interface(interface)
-    payload = {"candidate": self_ip + ":" + str(args.port)}
+    payload = {
+            "candidate": self_ip + ":" + str(args.port),
+            "term" : raft_term
+            }
     headers = {'Content-Type': 'application/json'}

     try:
@@ -236,15 +255,29 @@ def send_vote_request(voter_queen):
 @app.route('/request_vote', methods=['POST'])
 def request_vote():
     global last_heartbeat
+    global raft_term
+    global raft_lock

     last_heartbeat = int(time.time())

     if not request.json or not 'candidate' in request.json:
         abort(400)

-    log.info("got request for vote", candidate=request.json.get('candidate'))
+    if not request.json or not 'term' in request.json:
+        abort(400)

-    return jsonify({'result': 'OK'})
+    candidate = request.json.get('candidate')
+    term = request.json.get('term')
+
+    raft_lock.acquire()
+    log.info("got request for vote", candidate=candidate, term=term, current_term=raft_term)
+    if term > raft_term:
+        raft_term = term
+        raft_lock.release()
+        return jsonify({'result': 'OK'})
+
+    raft_lock.release()
+    return Response("{'reason': 'invalid term'}", status=300, mimetype='application/json')


 # Submit a task to the queen to be assigned to a drone
 ```

Adding the term is simple, we add the global variable and we initialize it to zero.
We also added a lock for anything we do in raft, so we can make sure our variables are
not being changed in multiple places, specifically the term variable.
 
We then modify our raft function so that it is aware of our raft lock, raft term, and
last heartbeat time. Then, when we become a candidate, the first thing we do is increase
our raft term to start the election. We then go out to and get votes from everyone with
our new term. Once we collect our votes, we also vote for ourselves, just like any good
politician would. Along with voting for ourselves, we reset our last heartbeat time 
just like we would if we got a vote request from another queen. Just like last time, if
we have enough votes, we switch from being a candidate to being a leader, and if we
lost the election we go back to being a follower.

A modification was made to when send votes to include the raft term, simple enough.
Finally, we modify the `request_vote` function to also be aware of our raft term and
raft lock. What we want to do is increment our raft term if someone sends us a raft term
higher than ours. If we see a raft term that matches ours, we reject the vote, as we
already have a leader with our current raft term.

With these changes, we've basically implemented leader election. The last thing we want to
do, in order to be fully consistent with the raft protocol is to abort our election if we
get a message from someone else saying they are the leader. After that we can reduce our
election timeouts from seconds to milliseconds and be fully raft.

To get this last part done, we want to switch from using the heartbeat function to the
actual raft `append_entries` function. We will be using this function in the future to actually
raft data between queens, but for now, we can use it as a heartbeat. Let's implement this:

```diff
diff --git a/larve.py b/larve.py
index 87c0676..5888110 100755
--- a/larve.py
+++ b/larve.py
@@ -45,10 +45,6 @@ class RaftState(Enum):
     LEADER = 3


-# The unix time (in seconds) we last heard from someone
-last_heartbeat = int(time.time())
-
-
 # Create the Flask API server
 app = Flask(__name__)

@@ -62,7 +58,7 @@ larve_verson = '0.0.1'
 interface = ""

 # Our leader timeout is anywhere between 5 and 15 seconds
-raft_election_timeout = random.randint(5, 15)
+raft_election_timeout = random.randint(150, 300)
 raft_state = RaftState.FOLLOWER
 raft_term = 0
 raft_lock = threading.Lock()
@@ -75,6 +71,14 @@ drones_lock = threading.Lock()
 queens = []


+def get_time_millis():
+    return int(round(time.time() * 1000))
+
+
+# The unix time (in seconds) we last heard from someone
+last_heartbeat = get_time_millis()
+
+
 # Function for the heartbeat thread
 def queen_heartbeat():
     global drones
@@ -84,7 +88,6 @@ def queen_heartbeat():
     # We always want to be heartbeating
     while True:
         if raft_state == RaftState.LEADER:
-            log.info("starting task", task="drone heartbeat")
             drones_lock.acquire()
             to_remove = []
             for k, v in drones.items():
@@ -113,7 +116,6 @@ def queen_heartbeat():
                 drones.pop(r, None)

             drones_lock.release()
-            log.info("completed task", task="drone heartbeat")
         time.sleep(10)


@@ -122,40 +124,49 @@ def raft():
     global raft_term
     global raft_lock
     global last_heartbeat
+    global raft_election_timeout

     # We're always doing raft
     while True:

         if raft_state == RaftState.FOLLOWER:
-            if (int(time.time()) - last_heartbeat) > raft_election_timeout:
+            if (get_time_millis() - last_heartbeat) > raft_election_timeout:
                 raft_state = RaftState.CANDIDATE
                 log.info("Changing raft state", previous=str(RaftState.FOLLOWER), next=str(RaftState.CANDIDATE))
             else:
-                time.sleep(1)
+                time.sleep(10/1000.0)

         if raft_state == RaftState.CANDIDATE:
             log.info("starting vote pool")
+            raft_election_timeout = random.randint(150,300)
             raft_lock.acquire()
             raft_term = raft_term + 1
             raft_lock.release()
             num_votes = sum(do_list_threaded(send_vote_request_thread, queens))
             # Vote for ourselves
             num_votes = num_votes + 1
-            last_heartbeat = int(time.time())
+            last_heartbeat = get_time_millis()
             votes_needed = int(math.ceil((len(queens) + 1)/2.0))
             log.info("got votes", count = num_votes, needed=votes_needed, term=raft_term)
+
+            # If we had aborted the election early, then we can ignore all our votes
+            raft_lock.acquire()
+            if raft_state == RaftState.FOLLOWER:
+                num_votes = 0
+            raft_lock.release()
+
             # Check to see if we have a majority of votes
+            raft_lock.acquire()
             if num_votes > votes_needed:
                 log.info("Changing raft state", previous=str(RaftState.CANDIDATE), next=str(RaftState.LEADER))
                 raft_state = RaftState.LEADER
             else:
                 log.info("Changing raft state", previous=str(RaftState.CANDIDATE), next=str(RaftState.FOLLOWER))
                 raft_state = RaftState.FOLLOWER
+            raft_lock.release()
         if raft_state == RaftState.LEADER:
-            log.info("doing raft task", task="leader heartbeat")
-            do_list_threaded(send_heartbeat_thread, queens)
-            log.info("completed raft task", task="leader heartbeat")
-            time.sleep(3)
+            do_list_threaded(send_append_entries_thread, queens)
+            time.sleep(100/1000.0)


 def do_list_threaded(func, to_do):
@@ -190,7 +201,7 @@ def healthz():
     global drones
     global last_heartbeat

-    last_heartbeat = int(time.time())
+    last_heartbeat = get_time_millis()

     current_health = {
         "status": str(larve_status),
@@ -209,6 +220,63 @@ def healthz():
     return jsonify(current_health)


+def send_append_entries_thread(host, idx, ret_list):
+     send_append_entries(host)
+
+
+def send_append_entries(host):
+    self_ip = get_ip_of_interface(interface)
+    payload = {
+        "leader": self_ip + ":" + str(args.port),
+        "term": raft_term,
+        "entries": []
+        }
+    headers = {'Content-Type': 'application/json'}
+    try:
+        requests.post('http://' + host + '/append_entries',
+                             headers=headers,
+                             data=json.dumps(payload))
+    except Exception as e:
+        pass
+
+
+@app.route('/append_entries', methods=['POST'])
+def append_entries():
+    global raft_term
+    global raft_state
+    global raft_lock
+    global last_heartbeat
+
+    if not request.json or not 'leader' in request.json:
+        abort(400)
+    if not request.json or not 'term' in request.json:
+        abort(400)
+    if not request.json or not 'entries' in request.json:
+        abort(400)
+
+    raft_lock.acquire()
+    if raft_state == RaftState.CANDIDATE:
+        # We are a candidate and we got an append entries
+        entry_term = int(request.json.get('term'))
+        leader = request.json.get('leader')
+        if entry_term >= raft_term:
+            log.info("Aborting candidate state", term=entry_term, leader=leader)
+            last_heartbeat = get_time_millis()
+            raft_term = entry_term
+            raft_state = RaftState.FOLLOWER
+            log.info("Changing raft state", previous=str(RaftState.CANDIDATE), next=str(RaftState.FOLLOWER))
+            raft_lock.release()
+            return jsonify({'result': 'OK'})
+        else:
+            raft_lock.release()
+            abort(400)
+
+    # If we had entries, do stuff with them here
+    last_heartbeat = get_time_millis()
+    raft_lock.release()
+    return jsonify({'result': 'OK'})
+
+
 def send_vote_request_thread(voter_queen, idx, ret_list):
     val = send_vote_request(voter_queen)
     ret_list[idx] = val
@@ -258,7 +326,7 @@ def request_vote():
     global raft_term
     global raft_lock

-    last_heartbeat = int(time.time())
+    last_heartbeat = get_time_millis()

     if not request.json or not 'candidate' in request.json:
         abort(400)
```

Our `append_entries` function is pretty simple. If we are in a candidate state and
we got an append entry request from someone who has a higher or equal term than us,
we know that they are the leader, so we take their term, set our state to follower,
and update our heartbeat time. In any other state, we just update our heartbeat
for now. We also add the corresponding send and send thread functions for this.

We've also added a helper function for getting the time in milliseconds. With that,
we've also changed all our times from seconds to milliseconds. Now, we've changed
our election timeout to be between 150 and 300 milliseconds versus our previous 5 to
15 seconds. We've also updated any `time.sleep()` calls we have to match our
millisecond change. The eagle eyed reader would also spot the addition of this 
line:

```diff
+            raft_election_timeout = random.randint(150,300)
```

We do this right after we become a candidate. The reasoning behind randomizing our
election timeout every time we start an election is to add entropy between elections,
reducing the chance that an election might fail in lockstep with another candidate.

All this in tow, we can now say that our leader election is complete! Running our
queens using our helper scripts we see everything come up and nearly instantly elect
a leader queen. If we were to kill that queen, then we would see that some other
queen would initiate an election with a new term and try and become leader. Fault
tolerant indeed! This is a huge milestone for our application, as we can start the
last part of our queen system: keeping data consistent between queens. Once we can
accomplish that, we can begin sending tasks from the queens to our drones,
communicate to the other queens what that task was, and keep a record of the state
of our drones, all while remaining fault tolerant. 

Some might ask why we are dealing with the problem of fault tolerance first, and
that is a fair question. The answer is that sending a task, of any kind, to a drone
is relatively easy. We're taking care of the difficult tasks first, so that when 
we start doing the more exciting things even faster.

In the next section, we will begin to transfer data between queens.
