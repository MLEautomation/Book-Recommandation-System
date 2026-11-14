import socket, subprocess, sys
host = socket.gethostbyname(socket.gethostname())
print("LAN URL: http://%s:8080" % host)
subprocess.call([sys.executable, "run.py"])
