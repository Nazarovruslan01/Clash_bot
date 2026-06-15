import os
import time
import json
import threading
from pathlib import Path
from collections import deque
from flask import Flask, render_template, jsonify, abort, request
from flask_cors import CORS

PATH = Path(__file__).parent
CACHE_PATH = PATH / "data" / "cache.json"
CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
NOTIFICATION_CACHE_SIZE = 3

app = Flask(__name__)
CORS(app)

class Instance:
    def __init__(
        self,
        id,
        run_status="",
        end_time=0,
        exclusions=None,
        notifications=None,
    ):
        self.id = id
        self.run_status = run_status
        self.end_time = end_time
        self.exclusions = exclusions if exclusions is not None else set()
        self.notifications = notifications if notifications is not None else deque(maxlen=NOTIFICATION_CACHE_SIZE)
    
    def __eq__(self, other):
        return self.id == other.id
    
    def __hash__(self):
        return hash(self.id)
    
    def to_dict(self):
        return {
            "id": self.id,
            "run_status": self.run_status,
            "end_time": self.end_time,
            "exclusions": sorted(list(self.exclusions)),
            "notifications": list(self.notifications)
        }
    
    def get_notifications(self, limit=NOTIFICATION_CACHE_SIZE):
        return list(self.notifications)[-limit:]
    
    def add_notification(self, data):
        self.notifications.append({"time_stamp": time.time(), "data": str(data)})

instances = {}
_lock = threading.RLock()

def get_cache():
    try:
        with open(CACHE_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def get_known_instances():
    data = get_cache()
    known_instances = data.get("known_instances", {})
    for id in known_instances:
        id = str(id)
        info = known_instances[id]
        instances[id] = Instance(
            id,
            run_status=info.get("run_status", ""),
            end_time=info.get("end_time", 0),
            exclusions=set(info.get("exclusions", [])),
            notifications=deque(info.get("notifications", []), maxlen=NOTIFICATION_CACHE_SIZE)
        )

def update_known_instances():
    with _lock:
        data = {id: instances[id].to_dict() for id in instances}
        tmp_path = CACHE_PATH.with_suffix('.tmp')
        with open(tmp_path, "w") as f:
            json.dump({"known_instances": data}, f, indent=4)
        os.replace(tmp_path, CACHE_PATH)

@app.route("/", methods=["GET"])
def home():
    with _lock:
        ids = sorted(instances.keys())
    return render_template("home.html", ids=ids)

@app.route("/<id>", methods=["GET"])
def handle_instance(id):
    instance = instances.get(id)
    if not instance: abort(404)
    return render_template(
        "instance.html",
        id=id,
        end_time=instance.end_time,
        current_time=time.time(),
        notifications=instance.get_notifications(),
        exclusions=list(instance.exclusions),
        run_status=instance.run_status
    )

@app.route("/current_time", methods=["GET"])
def handle_current_time():
    return {"current_time": time.time()}

@app.route("/<id>/end_time", methods=["GET", "POST"])
def handle_end_time(id):
    instance = instances.get(id)
    if not instance: abort(404)
    if request.method == "POST":
        data = (request.json or {}).get("time", 0)
        with _lock:
            instance.end_time = int(data) * 60 + time.time()
            update_known_instances()
    
    return {"end_time": instance.end_time}

@app.route("/<id>/running", methods=["GET"])
def handle_running(id):
    instance = instances.get(id)
    if not instance: abort(404)
    return {"running": instance.end_time == 0 or instance.end_time > time.time()}

@app.route("/<id>/status", methods=["GET", "POST"])
def handle_status(id):
    instance = instances.get(id)
    if not instance: abort(404)
    if request.method == "POST":
        data = request.json or {}
        with _lock:
            instance.run_status = data.get("status", "")
            update_known_instances()

    return {"status": instance.run_status}

@app.route("/<id>/exclude", methods=["GET", "POST"])
def handle_exclude(id):
    instance = instances.get(id)
    if not instance: abort(404)
    if request.method == "POST":
        data = request.json or {}
        action = data.get("action", "")
        item = str(data.get("item", "")).strip()
        if not item:
            return jsonify({"status": "error", "message": "Invalid item"}), 400
        with _lock:
            if action == "add":
                instance.exclusions.add(item)
            elif action == "remove":
                instance.exclusions.discard(item)
            update_known_instances()
    with _lock:
        return {"exclusions": sorted(list(instance.exclusions))}

@app.route("/<id>/notify", methods=["POST"])
def handle_notify(id):
    data = request.json
    if data is None:
        abort(400)
    instance = instances.get(id)
    if not instance: abort(404)
    with _lock:
        instance.add_notification(data)
        update_known_instances()
    return jsonify({"status": "success", "received": data})

@app.route("/<id>/notifications", methods=["GET", "POST"])
def handle_notifications(id):
    instance = instances.get(id)
    if not instance: abort(404)
    n = request.json if (request.method == "POST" and request.json is not None) else request.args.get("limit")
    limit = n if isinstance(n, int) else NOTIFICATION_CACHE_SIZE
    return jsonify(instance.get_notifications(limit))

@app.route("/instances", methods=["GET", "POST"])
def handle_instances():
    if request.method == "POST":
        data = request.json
        id = str(data.get("id", "")).strip()
        if id == "":
            return jsonify({"status": "error", "message": "Invalid ID"}), 400
        with _lock:
            if id not in instances:
                instances[id] = Instance(id)
                update_known_instances()
        return jsonify({"status": "success", "id": id})

    with _lock:
        return jsonify({"ids": sorted(instances.keys())})

@app.after_request
def add_cache_headers(response):
    if request.path.startswith("/static/"):
        # Cache static files for 30 days
        response.headers["Cache-Control"] = "public, max-age=2592000"
        response.headers.pop("Pragma", None)
        response.headers.pop("Expires", None)
    else:
        # No caching for dynamic routes
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

get_known_instances()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=1234, debug=False)