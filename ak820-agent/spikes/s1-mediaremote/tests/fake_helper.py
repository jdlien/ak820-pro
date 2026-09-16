#!/usr/bin/env python3
"""A stand-in for the MediaRemote helper, for the supervision tests.

    fake_helper.py MODE [TICK_SECONDS]

Like the real helper it says hello first and exits when stdin closes.
Modes:
  tick       tick forever
  fatal      tick three times, then `fatal` and exit(3) -- the designed recovery
  silent     one tick, then stay alive and say nothing: the wedge
  hello      say hello and exit at once, every run: a crash loop that proves nothing
  garbage    an unparseable line and a 2 MB line, then tick forever
"""
import json, os, sys, threading, time

mode = sys.argv[1]
tick = float(sys.argv[2]) if len(sys.argv) > 2 else 0.2

def emit(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()

def watch_stdin():
    for _ in sys.stdin:
        pass
    os._exit(0)          # the supervisor closed the pipe

threading.Thread(target=watch_stdin, daemon=True).start()
emit({"type": "hello", "pid": os.getpid()})
if mode == "hello":
    os._exit(1)
if mode == "garbage":
    sys.stdout.write("this is not json\n")
    sys.stdout.write("{\"type\":\"artwork\",\"data\":\"" + "A" * (2 << 20) + "\"}\n")
    sys.stdout.flush()
emit({"type": "now", "bundle": "com.example.Fake", "playing": True, "title": "T", "stale": False})
seq = 0
while True:
    time.sleep(tick)
    seq += 1
    if mode == "silent" and seq > 1:
        continue
    emit({"type": "tick", "seq": seq})
    if mode == "fatal" and seq == 3:
        emit({"type": "fatal", "error": "MediaRemote stopped answering; restarting"})
        os._exit(3)
