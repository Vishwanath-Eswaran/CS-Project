
from threading import Thread
import csv
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from vsepr.database import (
    create_user,
    find_user,
    initialize_user_database,
    list_molecule_names,
    remember_user_search,
    user_database_cursor,
)
from vsepr.nameProcessing import (
    carbon_map,
    load_molecule_map,
    save_molecule_map,
)

BASE_DIR = r"C:\Users\vishw\OneDrive\Desktop\CS Project\CS Project\version 2"
DATA_DIR = BASE_DIR + r"\data"
LOCAL_DATA_DIR = DATA_DIR + r"\local"
STATIC_DIR = BASE_DIR + r"\static"
SESSION_FILE = LOCAL_DATA_DIR + r"\session.txt"
INDEX_FILE = STATIC_DIR + r"\index.html"
SIGNIN_FILE = STATIC_DIR + r"\signin.html"
PROFILE_FILE = STATIC_DIR + r"\profile.html"
VPYTHON_FILE = STATIC_DIR + r"\vpython_page.html"
ELEMENTS_FILE = DATA_DIR + r"\elements.csv"
MOLECULE_NAMES_FILE = DATA_DIR + r"\molecule_names.txt"
VPYTHON_VIEWER_FILE = BASE_DIR + r"\vsepr\vpython_viewer.py"
viewer_process = None

app = Flask(__name__)


def load_elements_csv():
    elements = {}
    with open(ELEMENTS_FILE, "r", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = (row.get("symbol") or "").strip()
            if not symbol:
                continue
            elements[symbol] = {
                "name": row.get("name", ""),
                "color": row.get("color", "#FFFFFF"),
                "covalent_radius_pm": row.get("covalent_radius_pm", ""),
                "atomic_number": row.get("atomic_number", ""),
            }
    return elements


def load_molecule_names_csv():
    names = []
    with open(MOLECULE_NAMES_FILE, "r", ) as handle:
        for line in handle:
            cleaned = line.strip()
            if cleaned:
                names.append(cleaned)
    return names





def ensure_session_store():
    Path(LOCAL_DATA_DIR).mkdir(parents=True, exist_ok=True)
    if not Path(SESSION_FILE).exists():
        with open(SESSION_FILE, "w", encoding="utf-8") as handle:
            handle.write("")


def get_logged_in_user():
    ensure_session_store()
    with open(SESSION_FILE, "r", encoding="utf-8") as handle:
        username = handle.read().strip()
    return username or None


def set_logged_in_user(username):
    ensure_session_store()
    with open(SESSION_FILE, "w", encoding="utf-8") as handle:
        handle.write(username)


def clear_logged_in_user():
    ensure_session_store()
    with open(SESSION_FILE, "w", encoding="utf-8") as handle:
        handle.write("")


def build_user_profile(username):
    user = find_user(username)
    if user is None:
        clear_logged_in_user()
        return None

    user_id = user["user_id"]
    class_name = user["class_name"]
    with user_database_cursor() as database:
        database.execute(
            """
            SELECT molecule_name AS name, search_count AS searches, last_searched
            FROM user_molecules
            WHERE user_id = %s
            ORDER BY last_searched DESC, molecule_name
            LIMIT 10
            """,
            (user_id,),
        )
        recent = [
            {
                "name": row["name"],
                "searches": int(row["searches"]),
                "last_searched": row["last_searched"].isoformat() if row["last_searched"] else None,
            }
            for row in database.fetchall()
        ]

        database.execute(
            """
            SELECT molecule_name AS name, SUM(search_count) AS searches
            FROM user_molecules
            JOIN users USING (user_id)
            WHERE class_name = %s
            GROUP BY molecule_name
            ORDER BY searches DESC, molecule_name
            LIMIT 5
            """,
            (class_name,),
        )
        class_recommendations = [
            {"name": row["name"], "searches": int(row["searches"])}
            for row in database.fetchall()
        ]

        database.execute(
            """
            SELECT molecule_name AS name, search_count AS searches
            FROM user_molecules
            WHERE user_id = %s
            ORDER BY last_searched DESC, molecule_name
            LIMIT 5
            """,
            (user_id,),
        )
        personal_recommendations = [
            {"name": row["name"], "searches": int(row["searches"])}
            for row in database.fetchall()
        ]

    return {
        "username": username,
        "class_name": class_name,
        "recent_searches": recent,
        "class_recommendations": class_recommendations,
        "personal_recommendations": personal_recommendations,
    }


def molecule_for_identifier(identifier):
    cache_key = identifier.lower()
    molecules = load_molecule_map()
    if cache_key in molecules:
        return molecules[cache_key]

    lookup_identifier = int(identifier) if identifier.isdigit() else identifier
    molecular_map = carbon_map(lookup_identifier)
    molecules[cache_key] = molecular_map
    save_molecule_map(molecules)
    return molecular_map


def start_vpython_viewer(identifier, scene_width):
    global viewer_process
    if viewer_process is not None and viewer_process.poll() is None:
        viewer_process.terminate()
        viewer_process.wait(timeout=3)

    viewer_kwargs = {"cwd": BASE_DIR}
    if sys.platform.startswith("win"):
        viewer_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        viewer_kwargs["start_new_session"] = True

    viewer_process = subprocess.Popen(
        [
            sys.executable,
            VPYTHON_VIEWER_FILE,
            identifier,
            str(scene_width),
            "600",
        ],
        **viewer_kwargs,
    )


@app.route("/")
def home():
    return send_file(INDEX_FILE)


@app.route("/signin.html")
def signin_page():
    return send_file(SIGNIN_FILE)


@app.route("/profile")
def profile_page():
    return send_file(PROFILE_FILE)


@app.route("/vpython")
def vpython_page():
    return send_file(VPYTHON_FILE)


@app.route("/api/session")
def api_session():
    username = get_logged_in_user()
    if username is None:
        return jsonify({"error": "Not signed in."}), 401
    user = find_user(username)
    if user is None:
        clear_logged_in_user()
        return jsonify({"error": "Not signed in."}), 401
    return jsonify({"username": username, "class_name": user["class_name"]})


@app.route("/api/profile")
def api_profile():
    username = get_logged_in_user()
    if username is None:
        return jsonify({"error": "Sign in to view your profile."}), 401
    profile = build_user_profile(username)
    if profile is None:
        return jsonify({"error": "Sign in to view your profile."}), 401
    return jsonify(profile)


@app.route("/api/recommendations")
def api_recommendations():
    username = get_logged_in_user()
    if username is None:
        return jsonify({"error": "Sign in to see recommendations."}), 401
    profile = build_user_profile(username)
    if profile is None:
        return jsonify({"error": "Sign in to see recommendations."}), 401
    return jsonify({
        "class_recommendations": profile["class_recommendations"],
        "personal_recommendations": profile["personal_recommendations"],
    })


@app.route("/api/data")
def api_data():
    molecule_names = list_molecule_names()
    return jsonify({
        "elements": load_elements_csv(),
        "molecule_names": load_molecule_names_csv() + molecule_names,
    })


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Provide username, password, and class."}), 400
    username = data.get("username")
    password = data.get("password")
    class_name = data.get("class_name")

    if (
        not isinstance(username, str)
        or not 3 <= len(username.strip()) <= 30
        or not isinstance(password, str)
        or not 6 <= len(password) <= 255
        or not isinstance(class_name, str)
        or class_name.strip() not in {"6", "7", "8", "9", "10", "11", "12"}
    ):
        return jsonify({"error": "Invalid username, password, or class."}), 400
    username = username.strip()
    class_name = class_name.strip()

    user = find_user(username)
    if user is not None and user["password_hash"].startswith("pbkdf2_sha256$"):
        return jsonify({
            "error": (
                "This account was created with Version 1 password hashing. "
                "No-hashing mode cannot verify it; use a new username."
            )
        }), 409
    if (
        user is not None
        and user["password_hash"] == password
        and user["class_name"] == class_name
    ):
        set_logged_in_user(username)
        return jsonify({"message": "Signed in successfully."}), 200

    return jsonify({"error": "Username, password, or class is incorrect."}), 401


@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Provide username, password, and class."}), 400
    username = data.get("username")
    password = data.get("password")
    class_name = data.get("class_name")

    if (
        not isinstance(username, str)
        or not 3 <= len(username.strip()) <= 30
        or not isinstance(password, str)
        or not 6 <= len(password) <= 255
        or not isinstance(class_name, str)
        or class_name.strip() not in {"6", "7", "8", "9", "10", "11", "12"}
    ):
        return jsonify({"error": "Invalid username, password, or class."}), 400
    username = username.strip()
    class_name = class_name.strip()

    if find_user(username) is not None:
        return jsonify({"error": "That username already exists."}), 409
    create_user(username, password, class_name)
    set_logged_in_user(username)
    return jsonify({"message": "Account created successfully."}), 200


@app.route("/api/logout", methods=["POST"])
def api_logout():
    clear_logged_in_user()
    return jsonify({"message": "Signed out."}), 200


@app.route("/api/molecule", methods=["POST"])
def api_molecule():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Provide a molecule name or PubChem CID."}), 400
    identifier = data.get("identifier")
    if (
        not isinstance(identifier, str)
        or not identifier.strip()
        or len(identifier.strip()) > 255
    ):
        return jsonify({"error": "Enter a molecule name or PubChem CID."}), 400
    identifier = identifier.strip()
    scene_width = data.get("scene_width", 960)
    if (
        not isinstance(scene_width, int)
        or isinstance(scene_width, bool)
        or not 320 <= scene_width <= 4096
    ):
        return jsonify({"error": "Invalid viewer width."}), 400
    molecule_for_identifier(identifier)
    start_vpython_viewer(identifier.lower(), scene_width)
    username = get_logged_in_user()
    if username is not None:
        user = find_user(username)
        if user is not None:
            remember_user_search(user["user_id"], identifier)
        else:
            clear_logged_in_user()
    return jsonify({"message": "Molecule opened in the VPython viewer."}), 200


def start_flask():
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    Path(LOCAL_DATA_DIR).mkdir(parents=True, exist_ok=True)
    initialize_user_database()

    Thread(target=start_flask, daemon=True).start()
    time.sleep(1)
    webbrowser.open("http://127.0.0.1:5000")

    print("Open the app and choose the VPython page.")
    while True:
        time.sleep(1)
