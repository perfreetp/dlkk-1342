import httpx
import time
import sys

base = "http://localhost:8000/api/v1"
errors = []
checks = 0


def check(name, condition, detail=""):
    global checks
    checks += 1
    if condition:
        print(f"  OK: {name}")
    else:
        msg = f"FAIL: {name}" + (f" - {detail}" if detail else "")
        print(f"  {msg}")
        errors.append(msg)


print("\n=== Fix 1: Task timeline with source tracking ===")

task = httpx.post(f"{base}/tasks/", json={
    "name": "Timeline test", "task_type": "inspection"
}).json()
check("task created as draft", task["status"] == "draft")

# Start manually
started = httpx.post(f"{base}/tasks/{task['id']}/start").json()
check("manual start -> in_progress", started["status"] == "in_progress")

# Get timeline
timeline = httpx.get(f"{base}/tasks/{task['id']}/timeline").json()
check("timeline returns list", isinstance(timeline, list))
check("timeline has events", len(timeline) > 0, f"got {len(timeline)}")

if timeline:
    first = timeline[0]
    check("timeline has event_type", "event_type" in first)
    check("timeline has source", "source" in first)
    check("timeline has old_status", "old_status" in first)
    check("timeline has new_status", "new_status" in first)
    check("timeline has timestamp", "timestamp" in first)
    check("first event is status_changed", first["event_type"] == "status_changed")
    check("first event source is manual", first["source"] == "manual",
          f"got {first.get('source')}")

# Create device and report flight events
dev = httpx.post(f"{base}/devices/", json={
    "name": "TL-Drone", "device_type": "drone", "serial_number": "TL-001"
}).json()
httpx.put(f"{base}/devices/{dev['id']}", json={"status": "online"})
dev = httpx.get(f"{base}/devices/{dev['id']}").json()
check("device set to online", dev["status"] == "online")

# Takeoff should auto-advance task AND add flight event to timeline
tk = httpx.post(f"{base}/flights/events", json={
    "device_id": dev["id"], "task_id": task["id"],
    "event_type": "takeoff", "latitude": 30.0, "longitude": 120.0
}).json()
check("takeoff recorded", tk["event_type"] == "takeoff")

time.sleep(1.1)

# Waypoint reached
wp = httpx.post(f"{base}/flights/events", json={
    "device_id": dev["id"], "task_id": task["id"],
    "event_type": "waypoint_reached", "latitude": 30.1, "longitude": 120.1
}).json()
check("waypoint reached recorded", wp["event_type"] == "waypoint_reached")

time.sleep(1.1)

# Return home
rh = httpx.post(f"{base}/flights/events", json={
    "device_id": dev["id"], "task_id": task["id"],
    "event_type": "return_home", "latitude": 30.0, "longitude": 120.0
}).json()
check("return home recorded", rh["event_type"] == "return_home")

# Get full timeline again
timeline2 = httpx.get(f"{base}/tasks/{task['id']}/timeline").json()
check("timeline has more events", len(timeline2) > len(timeline))

# Check for flight events in timeline
flight_events = [e for e in timeline2 if e["event_type"].startswith("flight_")]
check("timeline has flight events", len(flight_events) >= 3,
      f"got {len(flight_events)} flight events")

if flight_events:
    check("flight event source is flight", flight_events[0]["source"] == "flight",
          f"got {flight_events[0].get('source')}")

# Check final status
task_final = httpx.get(f"{base}/tasks/{task['id']}").json()
check("task is completed after return_home", task_final["status"] == "completed",
      f"got {task_final['status']}")

# Nonexistent task timeline returns 404
bad_tl = httpx.get(f"{base}/tasks/99999/timeline")
check("nonexistent task timeline -> 404", bad_tl.status_code == 404)


print("\n=== Fix 2: Enhanced flight summaries ===")

# Report some positions
for i in range(5):
    httpx.post(f"{base}/flights/positions", json={
        "device_id": dev["id"], "task_id": task["id"],
        "latitude": 30.0 + i * 0.02, "longitude": 120.0 + i * 0.02,
        "altitude": 50 + i * 10, "battery_percent": 90 - i * 10
    })

# By-task summary with enhanced fields
by_task = httpx.get(f"{base}/devices/flight-summary/by-task",
                     params={"device_id": dev["id"]}).json()
check("by-task returns list", isinstance(by_task, list))
if by_task:
    s = by_task[0]
    check("by-task has first_flight_time", "first_flight_time" in s)
    check("by-task has last_flight_time", "last_flight_time" in s)
    check("by-task has position_count", "position_count" in s)
    check("by-task flight_count >= 1", s["flight_count"] >= 1)
    check("by-task position_count > 0", s["position_count"] > 0,
          f"got {s['position_count']}")
    check("by-task has min_latitude", s.get("min_latitude") is not None)
    check("by-task has max_latitude", s.get("max_latitude") is not None)

# By-day summary with per-task breakdown
now = time.time()
start_d = time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime(now - 86400))
end_d = time.strftime("%Y-%m-%dT23:59:59Z", time.gmtime(now + 86400))

by_day = httpx.get(f"{base}/devices/flight-summary/by-day",
                    params={"device_id": dev["id"], "start_date": start_d, "end_date": end_d}).json()
check("by-day returns list", isinstance(by_day, list))
check("by-day has entries", len(by_day) >= 1, f"got {len(by_day)}")

if by_day:
    d = by_day[0]
    check("by-day has date field", "date" in d and len(d["date"]) == 10)  # YYYY-MM-DD
    check("by-day has flight_count", "flight_count" in d)
    check("by-day has total_flight_hours", "total_flight_hours" in d)
    check("by-day has task_breakdown", "task_breakdown" in d,
          f"keys: {list(d.keys())}")
    check("task_breakdown is list", isinstance(d.get("task_breakdown"), list))

    if d.get("task_breakdown"):
        tb = d["task_breakdown"][0]
        check("task_breakdown has task_id", "task_id" in tb)
        check("task_breakdown has task_name", "task_name" in tb)
        check("task_breakdown has flight_count", "flight_count" in tb)
        check("task_breakdown has total_flight_hours", "total_flight_hours" in tb)


print("\n=== Fix 3: Delivery tracking with retries ===")

# Register subscription with bad URL
sub = httpx.post(f"{base}/alerts/subscriptions", json={
    "subscriber_id": "retry-test",
    "event_types": ["alert.low_battery"],
    "callback_url": "http://127.0.0.1:19998/bad-callback"
}).json()
check("subscription registered", sub["subscriber_id"] == "retry-test")

# Trigger an alert (will fail callback)
httpx.post(f"{base}/flights/positions", json={
    "device_id": dev["id"],
    "latitude": 30.0, "longitude": 120.0, "altitude": 50, "battery_percent": 5
})

time.sleep(2)

# Get delivery log
log = httpx.get(f"{base}/alerts/delivery-log",
                 params={"subscriber_id": "retry-test"}).json()
check("delivery log returns list", isinstance(log, list))
if log:
    entry = log[0]
    check("log has delivery_id", "delivery_id" in entry)
    check("log has attempts list", "attempts" in entry and isinstance(entry["attempts"], list))
    check("log has first_attempt_at", "first_attempt_at" in entry)
    check("log has last_attempt_at", "last_attempt_at" in entry)

    if entry["attempts"]:
        a = entry["attempts"][0]
        check("attempt has attempt number", "attempt" in a)
        check("attempt has success", "success" in a)
        check("attempt has timestamp", "timestamp" in a)
        check("first attempt failed", a["success"] is False)
        check("failed attempt has error", a.get("error") is not None,
              f"error: {a.get('error')}")

# Get failed deliveries
failed = httpx.get(f"{base}/alerts/failed-deliveries",
                    params={"subscriber_id": "retry-test"}).json()
check("failed deliveries returns list", isinstance(failed, list))
check("failed deliveries has entries", len(failed) >= 1,
      f"got {len(failed)}")

# Manual retry
retry_resp = httpx.post(f"{base}/alerts/subscriptions/retry-test/retry").json()
check("retry returns result", "retried_count" in retry_resp)
check("retry has total_failed", "total_failed" in retry_resp)
check("retried_count > 0", retry_resp["retried_count"] >= 1,
      f"got {retry_resp['retried_count']}")


print("\n=== Fix 4: Unified device availability rules ===")

# Test offline device
offline_dev = httpx.post(f"{base}/devices/", json={
    "name": "OfflineDrone", "device_type": "drone", "serial_number": "OFF-001"
}).json()
httpx.put(f"{base}/devices/{offline_dev['id']}", json={"status": "offline"})
offline_dev = httpx.get(f"{base}/devices/{offline_dev['id']}").json()
check("device set to offline", offline_dev["status"] == "offline")

# Test retired device
retired_dev = httpx.post(f"{base}/devices/", json={
    "name": "RetiredDrone", "device_type": "drone", "serial_number": "RET-001"
}).json()
httpx.put(f"{base}/devices/{retired_dev['id']}", json={"status": "retired"})
retired_dev = httpx.get(f"{base}/devices/{retired_dev['id']}").json()
check("device set to retired", retired_dev["status"] == "retired")

# Test maintenance device
maint_dev = httpx.post(f"{base}/devices/", json={
    "name": "MaintDrone", "device_type": "drone", "serial_number": "MNT-001"
}).json()
httpx.put(f"{base}/devices/{maint_dev['id']}", json={"status": "maintenance"})
maint_dev = httpx.get(f"{base}/devices/{maint_dev['id']}").json()
check("device set to maintenance", maint_dev["status"] == "maintenance")

# Assign offline device -> 400
task2 = httpx.post(f"{base}/tasks/", json={"name": "Assign test 2"}).json()
pilot_ok = httpx.post(f"{base}/devices/", json={
    "name": "Pilot OK", "device_type": "controller", "serial_number": "PILOT-OK"
}).json()

bad_assign1 = httpx.post(f"{base}/tasks/{task2['id']}/assign",
                          params={"pilot_id": pilot_ok["id"], "drone_id": offline_dev["id"]})
check("assign offline drone -> 400", bad_assign1.status_code == 400)
check("error mentions 'offline'", "offline" in bad_assign1.json().get("detail", "").lower(),
      f"detail: {bad_assign1.json().get('detail', '')}")

# Assign retired device -> 400
bad_assign2 = httpx.post(f"{base}/tasks/{task2['id']}/assign",
                          params={"pilot_id": pilot_ok["id"], "drone_id": retired_dev["id"]})
check("assign retired drone -> 400", bad_assign2.status_code == 400)
check("error mentions 'retired'", "retired" in bad_assign2.json().get("detail", "").lower(),
      f"detail: {bad_assign2.json().get('detail', '')}")

# Assign maintenance device -> 400
bad_assign3 = httpx.post(f"{base}/tasks/{task2['id']}/assign",
                          params={"pilot_id": pilot_ok["id"], "drone_id": maint_dev["id"]})
check("assign maintenance drone -> 400", bad_assign3.status_code == 400)
check("error mentions 'maintenance'", "maintenance" in bad_assign3.json().get("detail", "").lower())

# Offline device report position -> 400
bad_pos1 = httpx.post(f"{base}/flights/positions", json={
    "device_id": offline_dev["id"],
    "latitude": 30.0, "longitude": 120.0, "altitude": 50
})
check("offline device position -> 400", bad_pos1.status_code == 400)

# Retired device report position -> 400
bad_pos2 = httpx.post(f"{base}/flights/positions", json={
    "device_id": retired_dev["id"],
    "latitude": 30.0, "longitude": 120.0, "altitude": 50
})
check("retired device position -> 400", bad_pos2.status_code == 400)

# Maintenance device report event -> 400
bad_evt = httpx.post(f"{base}/flights/events", json={
    "device_id": maint_dev["id"], "event_type": "takeoff",
    "latitude": 30.0, "longitude": 120.0
})
check("maintenance device event -> 400", bad_evt.status_code == 400)

# Normal device still works
good_dev = httpx.post(f"{base}/devices/", json={
    "name": "GoodDrone", "device_type": "drone", "serial_number": "GOOD-001"
}).json()
httpx.put(f"{base}/devices/{good_dev['id']}", json={"status": "online"})
good_dev = httpx.get(f"{base}/devices/{good_dev['id']}").json()
good_pos = httpx.post(f"{base}/flights/positions", json={
    "device_id": good_dev["id"],
    "latitude": 30.0, "longitude": 120.0, "altitude": 50
})
check("online device position -> 200", good_pos.status_code == 200)


print("\n" + "=" * 50)
if errors:
    print(f"FAILED: {len(errors)} / {checks}")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print(f"ALL {checks} TESTS PASSED!")
    sys.exit(0)
