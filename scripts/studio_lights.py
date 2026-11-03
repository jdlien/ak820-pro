#!/usr/bin/env python3
"""The Studio's lights, for filmed gates: off with a snapshot, and back as they were.

    scripts/studio_lights.py status    # every Studio light and the accent switch, and the presence sensor
    scripts/studio_lights.py off       # snapshot into scene.ak820_bench_before, then all of them off
    scripts/studio_lights.py restore   # the snapshot back, each light as it was

Home Assistant over its REST API, with the token from the Keychain item
`home-assistant` (or $HA_TOKEN). The Studio's lights come from HA's own
area list, so a light added there is covered. Only `light.*` and the
allow-listed switches below are ever switched, so the presence sensor's
configuration switches and anything outside the Studio are never touched.

docs/test-bench.md ("The camera") says what a dark room does and does not
buy a filmed gate.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

HA_URL = os.environ.get("HA_URL", "https://ha.jdlien.ca")
AREA = "Studio"
SWITCHES = ["switch.accent_lights"]          # lights behind a switch, not a light entity
PRESENCE = "binary_sensor.seeedstudio_mmwave_kit_bf19cc_presence_information"
SCENE_ID = "ak820_bench_before"


def token():
    t = os.environ.get("HA_TOKEN") or subprocess.run(
        ["security", "find-generic-password", "-s", "home-assistant", "-w"],
        capture_output=True, text=True, timeout=10).stdout.strip()
    if not t:
        sys.exit("no Home Assistant token: the Keychain item home-assistant, or $HA_TOKEN")
    return t


def call(path, data=None):
    req = urllib.request.Request(
        HA_URL + path, data=None if data is None else json.dumps(data).encode(),
        headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read().decode()
    return json.loads(body) if body.strip().startswith(("{", "[")) else body


def entities():
    names = call("/api/template", {"template": f"{{{{ area_entities('{AREA}') | select('match', 'light\\\\.') | list | tojson }}}}"})
    found = names if isinstance(names, list) else json.loads(names)
    return sorted(found) + SWITCHES


def states(ids):
    return {e: call(f"/api/states/{e}")["state"] for e in ids}


def show(st):
    on = [e for e, s in st.items() if s == "on"]
    print(f"{len(on)} of {len(st)} on: " + (", ".join(on) if on else "none"))


def cmd_status(_):
    show(states(entities()))
    print(f"presence ({PRESENCE}): {call(f'/api/states/{PRESENCE}')['state']}")


def cmd_off(_):
    ids = entities()
    before = states(ids)
    call("/api/services/scene/create", {"scene_id": SCENE_ID, "snapshot_entities": ids})
    print(f"snapshot: scene.{SCENE_ID} ({len(ids)} entities)")
    lights = [e for e in ids if e.startswith("light.") and before[e] == "on"]
    switches = [e for e in ids if e.startswith("switch.") and before[e] == "on"]
    t = time.time()
    if lights:
        call("/api/services/light/turn_off", {"entity_id": lights})
    if switches:
        call("/api/services/switch/turn_off", {"entity_id": switches})
    time.sleep(2)
    after = states(ids)
    print(f"off at {time.strftime('%H:%M:%S', time.localtime(t))}: ", end="")
    show(after)


def cmd_restore(_):
    call("/api/services/scene/turn_on", {"entity_id": f"scene.{SCENE_ID}"})
    time.sleep(2)
    print("restored: ", end="")
    show(states(entities()))


def main():
    cmds = {"status": cmd_status, "off": cmd_off, "restore": cmd_restore}
    if len(sys.argv) != 2 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[sys.argv[1]](None)


if __name__ == "__main__":
    main()
