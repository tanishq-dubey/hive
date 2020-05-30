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
