"""Run the viewer after setting the MySQL connection environment variables."""

import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, make_response, request, send_from_directory
import pubchempy as pcp
import mysql.connector

try:
    from .element import ELEMENTS_BY_SYMBOL
    from .nameProcessing import carbon_map, load_molecule_map, save_molecule_map
except ImportError:  # pragma: no cover - direct script execution fallback
    from element import ELEMENTS_BY_SYMBOL
    from nameProcessing import carbon_map, load_molecule_map, save_molecule_map


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
MAX_REQUEST_SIZE = 4096
MAX_BUILDER_REQUEST_SIZE = 32768
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "cscproject")
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "root")
PASSWORD_HASH_ITERATIONS = 200_000
SESSION_COOKIE_NAME = "vsepr_session"
viewer_lock = threading.Lock()
viewer_process = None
session_lock = threading.Lock()
active_sessions = {}


def connect_user_database():
    """Connect to the configured MySQL database."""
    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
    )


@contextmanager
def user_database_cursor():
    """Open a dictionary cursor and finish its transaction safely."""
    connection = connect_user_database()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            yield cursor
            connection.commit()
        except mysql.connector.Error:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()


def initialize_user_database():
    """Create the MySQL database and its two student-data tables."""
    if not re.fullmatch(r"[A-Za-z0-9_]+", MYSQL_DATABASE):
        raise ValueError("MYSQL_DATABASE can contain only letters, numbers, and underscores.")

    server = mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
    )
    try:
        cursor = server.cursor()
        cursor.execute(
            "CREATE DATABASE IF NOT EXISTS `{}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci".format(
                MYSQL_DATABASE
            )
        )
        cursor.close()
    finally:
        server.close()

    with user_database_cursor() as database:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(30) NOT NULL UNIQUE,
                class_name VARCHAR(2) NOT NULL,
                password_hash VARCHAR(255) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS user_molecules (
                user_id INT NOT NULL,
                molecule_name VARCHAR(255) NOT NULL,
                search_count INT NOT NULL DEFAULT 1,
                last_searched DATETIME(6) NOT NULL,
                PRIMARY KEY (user_id, molecule_name),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )


def hash_password(password, salt=None):
    """Make a salted password hash that can be checked later."""
    salt = salt or secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return "{}${}${}${}".format(
        "pbkdf2_sha256",
        PASSWORD_HASH_ITERATIONS,
        salt.hex(),
        password_hash.hex(),
    )


def password_matches(password, saved_hash):
    """Check a password against the salted hash saved for the user."""
    try:
        algorithm, iterations, salt_hex, expected_hash = saved_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations)
        if not 100_000 <= iterations <= 1_000_000:
            return False
        actual_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            iterations,
        ).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual_hash, expected_hash)


def remember_user_search(user_id, molecule_name):
    """Count a molecule search for a signed-in student."""
    searched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    with user_database_cursor() as database:
        database.execute(
            """
            INSERT INTO user_molecules (
                user_id, molecule_name, search_count, last_searched
            )
            VALUES (%s, %s, 1, %s)
            ON DUPLICATE KEY UPDATE
                search_count = search_count + 1,
                last_searched = %s
            """,
            (user_id, molecule_name, searched_at, searched_at),
        )


def get_signed_in_user_id():
    """Find the user connected to this browser, if they are signed in."""
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token is None:
        return None
    with session_lock:
        return active_sessions.get(session_token)


def stop_vpython_viewer():
    """Stop the previous VPython scene process, if one is running."""
    global viewer_process
    with viewer_lock:
        if viewer_process is None:
            return
        process = viewer_process
        viewer_process = None
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def start_vpython_viewer(identifier, scene_width):
    """Start the project's VPython renderer on a port for the page iframe."""
    global viewer_process
    with viewer_lock:
        if viewer_process is not None and viewer_process.poll() is None:
            viewer_process.terminate()
            try:
                viewer_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                viewer_process.kill()
                viewer_process.wait()

        with socket.socket() as port_socket:
            port_socket.bind(("127.0.0.1", 0))
            port = port_socket.getsockname()[1]

        environment = os.environ.copy()
        environment["VPYTHON_NO_LAUNCH_BROWSER"] = "1"
        environment["VPYTHON_HTTP_PORT"] = str(port)
        viewer_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "vsepr.vpython_viewer",
                identifier,
                str(scene_width),
                "430",
            ],
            cwd=str(BASE_DIR),
            env=environment,
        )
        viewer_url = "http://127.0.0.1:{}/".format(port)
        deadline = time.monotonic() + 10
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    return viewer_url
            except OSError as error:
                if viewer_process.poll() is not None:
                    viewer_process = None
                    raise OSError("VPython exited before its scene server started.") from error
                if time.monotonic() >= deadline:
                    viewer_process.terminate()
                    viewer_process.wait()
                    viewer_process = None
                    raise OSError("VPython scene server did not start within 10 seconds.") from error
                time.sleep(0.05)


def molecule_for_identifier(identifier):
    """Load a cached molecule or look it up by name or PubChem CID."""
    cache_key = identifier.lower()
    molecules = load_molecule_map()
    if cache_key in molecules:
        return molecules[cache_key]

    lookup_identifier = int(identifier) if identifier.isdigit() else identifier
    molecular_map = carbon_map(lookup_identifier)
    molecules[cache_key] = molecular_map
    save_molecule_map(molecules)
    return molecular_map


def molecule_to_display_data(molecular_map):
    """Convert the adjacency map into atom and bond data for the browser."""
    atom_symbols = {}
    labels = list(molecular_map)
    for neighbors in molecular_map.values():
        labels.extend(neighbors)

    for label in labels:
        if label.startswith("lp"):
            symbol = "lp"
        else:
            match = re.match(r"[A-Z][a-z]?", label)
            if match is None:
                raise ValueError("Invalid atom label in molecule structure.")
            symbol = match.group(0)
        if symbol != "lp" and symbol not in ELEMENTS_BY_SYMBOL:
            raise ValueError("Unknown element in molecule structure: " + symbol)
        atom_symbols[label] = symbol

    atoms = []
    for label, symbol in atom_symbols.items():
        if symbol == "lp":
            atoms.append({
                "id": label,
                "label": "LP",
                "symbol": "lp",
                "color": "#A78BFA",
                "radius": 0.28,
            })
            continue
        element = ELEMENTS_BY_SYMBOL[symbol]
        atoms.append({
            "id": label,
            "label": symbol,
            "symbol": symbol,
            "color": element["color"],
            "radius": max(0.18, min(0.46, element["covalent_radius_pm"] / 190)),
        })

    bond_orders = {}
    for center, neighbors in molecular_map.items():
        neighbor_counts = Counter(neighbors)
        for neighbor, order in neighbor_counts.items():
            pair = tuple(sorted((center, neighbor)))
            bond_orders[pair] = max(bond_orders.get(pair, 0), order)

    atom_indexes = {atom["id"]: index for index, atom in enumerate(atoms)}
    bonds = [
        {
            "source": atom_indexes[first],
            "target": atom_indexes[second],
            "order": order,
        }
        for (first, second), order in bond_orders.items()
    ]
    return {"atoms": atoms, "bonds": bonds}


def saved_molecule_to_graph(molecular_map):
    """Convert a saved adjacency map into symbol-labeled undirected graph data."""
    labels = set(molecular_map)
    for neighbors in molecular_map.values():
        labels.update(neighbors)

    symbols = {}
    adjacency = {label: {} for label in labels}
    directed_counts = {}
    for label in labels:
        if label.startswith("lp"):
            symbols[label] = "lp"
        else:
            match = re.match(r"[A-Z][a-z]?", label)
            if match is None:
                raise ValueError("Invalid atom label in saved molecule.")
            symbols[label] = match.group(0)

    for label, neighbors in molecular_map.items():
        counts = Counter(neighbors)
        for neighbor, count in counts.items():
            if neighbor == label:
                return symbols, adjacency
            pair = tuple(sorted((label, neighbor)))
            directed_counts.setdefault(pair, {})[label] = count

    for (first, second), directions in directed_counts.items():
        order = max(directions.values())
        adjacency[first][second] = order
        adjacency[second][first] = order
    return symbols, adjacency


def find_cached_molecule_match(atom_symbols, molecule_bonds):
    """Find a saved molecule with the same atoms and bond connections."""
    user_adjacency = {atom_id: {} for atom_id in atom_symbols}
    for first, second in molecule_bonds:
        user_adjacency[first][second] = user_adjacency[first].get(second, 0) + 1
        user_adjacency[second][first] = user_adjacency[second].get(first, 0) + 1

    user_degrees = {
        atom_id: sum(neighbors.values())
        for atom_id, neighbors in user_adjacency.items()
    }

    for name, molecular_map in load_molecule_map().items():
        saved_symbols, saved_adjacency = saved_molecule_to_graph(molecular_map)
        if Counter(atom_symbols.values()) != Counter(saved_symbols.values()):
            continue
        saved_degrees = {
            label: sum(neighbors.values())
            for label, neighbors in saved_adjacency.items()
        }
        if Counter(user_degrees.values()) != Counter(saved_degrees.values()):
            continue

        candidates = {
            atom_id: [
                label
                for label in saved_symbols
                if saved_symbols[label] == atom_symbols[atom_id]
                and saved_degrees[label] == user_degrees[atom_id]
            ]
            for atom_id in atom_symbols
        }
        if any(not choices for choices in candidates.values()):
            continue

        search_order = sorted(
            atom_symbols,
            key=lambda atom_id: (
                len(candidates[atom_id]),
                -user_degrees[atom_id],
            ),
        )
        mapping = {}
        used_labels = set()

        def find_matching_atom(index):
            """Try each possible saved atom for the next builder atom."""
            if index == len(search_order):
                return True
            atom_id = search_order[index]
            for saved_label in candidates[atom_id]:
                if saved_label in used_labels:
                    continue
                if any(
                    user_adjacency[atom_id].get(other_id, 0)
                    != saved_adjacency[saved_label].get(saved_other_id, 0)
                    for other_id, saved_other_id in mapping.items()
                ):
                    continue
                mapping[atom_id] = saved_label
                used_labels.add(saved_label)
                if find_matching_atom(index + 1):
                    return True
                used_labels.remove(saved_label)
                del mapping[atom_id]
            return False

        if find_matching_atom(0):
            return name
    return None


app = Flask(__name__, static_folder=None)


def json_response(status, payload, headers=None):
    response = make_response(jsonify(payload), status)
    response.headers["Cache-Control"] = "no-store"
    for name, value in (headers or {}).items():
        response.headers[name] = value
    return response


def read_json_request(max_request_size):
    """Read a JSON object, returning an error response when the request is invalid."""
    try:
        content_length = int(request.headers.get("Content-Length", "0"))
    except ValueError:
        return None, json_response(400, {"error": "Invalid request size."})

    if content_length <= 0 or content_length > max_request_size:
        return None, json_response(413, {"error": "Request is too large."})

    try:
        request_data = json.loads(request.get_data(cache=False))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, json_response(400, {"error": "Request body must be valid JSON."})

    if not isinstance(request_data, dict):
        return None, json_response(
            400,
            {"error": "Provide a molecule name or PubChem CID."},
        )
    return request_data, None


def read_scene_width(request_data):
    """Get a valid viewer width or return an error response."""
    scene_width = request_data.get("scene_width", 960)
    if (
        not isinstance(scene_width, int)
        or isinstance(scene_width, bool)
        or not 320 <= scene_width <= 4096
    ):
        return None, json_response(400, {"error": "Invalid viewer width."})
    return scene_width, None


def send_viewer_response(
    molecule_name,
    display_name,
    scene_width,
    display_data,
    user_id=None,
    searched_name=None,
):
    """Start the 3D viewer and return its URL and molecule data."""
    try:
        viewer_url = start_vpython_viewer(molecule_name, scene_width)
    except OSError as error:
        return json_response(
            500,
            {"error": "Could not start the VPython viewer: " + str(error)},
        )

    if user_id is not None:
        try:
            remember_user_search(user_id, searched_name)
        except mysql.connector.Error as error:
            return json_response(
                500,
                {"error": "Could not save your molecule search: " + str(error)},
            )

    return json_response(
        200,
        {"name": display_name, "viewer_url": viewer_url, **display_data},
    )


def send_mysql_error(error):
    """Return a clear error if MySQL cannot complete a request."""
    return json_response(
        500,
        {"error": "Could not access MySQL. Check the connection settings: " + str(error)},
    )


def send_signed_in_user():
    """Return the name and class of the current user."""
    user_id = get_signed_in_user_id()
    if user_id is None:
        return json_response(401, {"error": "Sign in to continue."})
    with user_database_cursor() as database:
        database.execute(
            "SELECT username, class_name FROM users WHERE user_id = %s",
            (user_id,),
        )
        user = database.fetchone()
    if user is None:
        return json_response(401, {"error": "Sign in to continue."})
    return json_response(
        200,
        {"username": user["username"], "class_name": user["class_name"]},
    )


@app.get("/api/session")
def api_session():
    try:
        return send_signed_in_user()
    except mysql.connector.Error as error:
        return send_mysql_error(error)


@app.get("/api/recommendations")
def api_recommendations():
    """Return the user's history and the most searched molecules in their class."""
    user_id = get_signed_in_user_id()
    if user_id is None:
        return json_response(401, {"error": "Sign in to see recommendations."})

    try:
        with user_database_cursor() as database:
            database.execute(
                "SELECT class_name FROM users WHERE user_id = %s",
                (user_id,),
            )
            user = database.fetchone()
            if user is None:
                return json_response(401, {"error": "Sign in to see recommendations."})

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
                (user["class_name"],),
            )
            class_recommendations = database.fetchall()
            database.execute(
                """
                SELECT molecule_name AS name, search_count AS searches
                FROM user_molecules
                WHERE user_id = %s
                ORDER BY last_searched DESC
                LIMIT 5
                """,
                (user_id,),
            )
            personal_recommendations = database.fetchall()
    except mysql.connector.Error as error:
        return send_mysql_error(error)

    return json_response(
        200,
        {
            "class_recommendations": [
                {"name": row["name"], "searches": int(row["searches"])}
                for row in class_recommendations
            ],
            "personal_recommendations": [
                {"name": row["name"], "searches": int(row["searches"])}
                for row in personal_recommendations
            ],
        },
    )


@app.get("/api/elements")
def api_elements():
    elements = [
        {
            "symbol": symbol,
            "name": element["name"],
            "color": element["color"],
            "covalent_radius_pm": element["covalent_radius_pm"],
        }
        for symbol, element in sorted(
            ELEMENTS_BY_SYMBOL.items(),
            key=lambda item: item[1]["atomic_number"],
        )
    ]
    return json_response(200, {"elements": elements})


@app.get("/api/molecules")
def api_molecules():
    molecules = load_molecule_map()
    names_path = DATA_DIR / "molecule_names.txt"
    names = []
    if names_path.exists():
        names.extend(
            line.strip()
            for line in names_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    names.extend(molecules)
    unique_names = {}
    for name in names:
        unique_names.setdefault(name.lower(), name)
    return json_response(200, {"molecules": list(unique_names.values())})


def account_details(request_data):
    """Check the account fields shared by registration and sign-in."""
    username = request_data.get("username")
    password = request_data.get("password")
    class_name = request_data.get("class_name")
    if (
        not isinstance(username, str)
        or not 3 <= len(username.strip()) <= 30
        or not isinstance(password, str)
        or len(password) < 6
        or class_name not in ("6", "7", "8", "9", "10", "11", "12")
    ):
        return None, json_response(
            400,
            {"error": "Enter a 3–30 character username, password (at least 6 characters), and a grade from 6 to 12."},
        )
    return (username.strip(), password, class_name), None


def start_user_session(user_id, username, class_name):
    """Sign the user in and set a browser cookie."""
    session_token = secrets.token_urlsafe(32)
    with session_lock:
        active_sessions[session_token] = user_id
    response = json_response(
        200,
        {"username": username, "class_name": class_name},
    )
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        path="/",
        httponly=True,
        samesite="Lax",
    )
    return response


def register_account(request_data):
    """Create a student account and sign them in."""
    account, error_response = account_details(request_data)
    if error_response is not None:
        return error_response
    username, password, class_name = account
    try:
        with user_database_cursor() as database:
            database.execute(
                """
                INSERT INTO users (username, class_name, password_hash)
                VALUES (%s, %s, %s)
                """,
                (username, class_name, hash_password(password)),
            )
            user_id = database.lastrowid
    except mysql.connector.IntegrityError:
        return json_response(
            409,
            {"error": "That username is already taken. Try signing in instead."},
        )
    return start_user_session(user_id, username, class_name)


def login_account(request_data):
    """Check the username, password, and selected class, then sign in."""
    account, error_response = account_details(request_data)
    if error_response is not None:
        return error_response
    username, password, class_name = account
    with user_database_cursor() as database:
        database.execute(
            """
            SELECT user_id, username, class_name, password_hash
            FROM users
            WHERE username = %s
            """,
            (username,),
        )
        user = database.fetchone()
    if (
        user is None
        or user["class_name"] != class_name
        or not password_matches(password, user["password_hash"])
    ):
        return json_response(
            401,
            {"error": "Username, password, or class is incorrect."},
        )
    return start_user_session(
        user["user_id"],
        user["username"],
        user["class_name"],
    )


def logout_account():
    """Remove the current login and clear the browser cookie."""
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token is not None:
        with session_lock:
            active_sessions.pop(session_token, None)
    response = json_response(200, {"message": "Signed out."})
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="Lax",
    )
    return response


def do_molecule_search(request_data):
    """Look up a molecule by name or CID and show it in the viewer."""
    identifier = request_data.get("identifier")
    if not isinstance(identifier, str) or not identifier.strip():
        return json_response(400, {"error": "Enter a molecule name or PubChem CID."})
    identifier = identifier.strip()
    scene_width, error_response = read_scene_width(request_data)
    if error_response is not None:
        return error_response

    try:
        molecular_map = molecule_for_identifier(identifier)
        display_data = molecule_to_display_data(molecular_map)
    except ValueError as error:
        return json_response(404, {"error": str(error)})
    except (pcp.PubChemHTTPError, OSError, TimeoutError):
        return json_response(
            502,
            {"error": "PubChem could not be reached. Try a saved molecule or retry shortly."},
        )
    return send_viewer_response(
        identifier.lower(),
        identifier,
        scene_width,
        display_data,
        user_id=get_signed_in_user_id(),
        searched_name=identifier,
    )


def read_builder_atoms(atoms):
    """Check each builder atom and return its ID-to-element mapping."""
    atom_symbols = {}
    for atom_data in atoms:
        if not isinstance(atom_data, dict):
            return None, json_response(400, {"error": "Invalid atom data."})
        atom_id = atom_data.get("id")
        symbol = atom_data.get("symbol")
        if (
            not isinstance(atom_id, int)
            or isinstance(atom_id, bool)
            or not isinstance(symbol, str)
            or (symbol != "lp" and symbol not in ELEMENTS_BY_SYMBOL)
            or atom_id in atom_symbols
        ):
            return None, json_response(400, {"error": "Invalid or duplicate atom."})
        atom_symbols[atom_id] = symbol
    return atom_symbols, None


def read_builder_bonds(bonds, atom_symbols):
    """Check each builder bond and return its pair of atom IDs."""
    molecule_bonds = []
    seen_bonds = set()
    for bond in bonds:
        if not isinstance(bond, dict):
            return None, json_response(400, {"error": "Invalid bond data."})
        first = bond.get("first")
        second = bond.get("second")
        if (
            not isinstance(first, int)
            or isinstance(first, bool)
            or not isinstance(second, int)
            or isinstance(second, bool)
            or first not in atom_symbols
            or second not in atom_symbols
            or first == second
        ):
            return None, json_response(400, {"error": "Bond references an invalid atom."})
        pair = tuple(sorted((first, second)))
        if pair in seen_bonds:
            return None, json_response(400, {"error": "Duplicate bond."})
        seen_bonds.add(pair)
        molecule_bonds.append(pair)
    return molecule_bonds, None


def visualize_built_molecule(request_data):
    """Validate a builder structure and render it if it is in the saved library."""
    atoms = request_data.get("atoms")
    bonds = request_data.get("bonds")
    scene_width, error_response = read_scene_width(request_data)
    if error_response is not None:
        return error_response
    if not isinstance(atoms, list) or not atoms or len(atoms) > 200:
        return json_response(400, {"error": "Add between 1 and 200 atoms first."})
    if not isinstance(bonds, list) or len(bonds) > 400:
        return json_response(400, {"error": "Invalid molecule bonds."})

    atom_symbols, error_response = read_builder_atoms(atoms)
    if error_response is not None:
        return error_response
    molecule_bonds, error_response = read_builder_bonds(bonds, atom_symbols)
    if error_response is not None:
        return error_response

    matched_name = find_cached_molecule_match(atom_symbols, molecule_bonds)
    if matched_name is None:
        return json_response(
            404,
            {"error": "This structure is not in the saved molecule library, so it was not rendered."},
        )

    molecules = load_molecule_map()
    display_data = molecule_to_display_data(molecules[matched_name])
    return send_viewer_response(
        matched_name,
        matched_name.title(),
        scene_width,
        display_data,
    )


@app.post("/api/molecule")
@app.post("/api/visualize-built")
@app.post("/api/account/register")
@app.post("/api/account/login")
@app.post("/api/account/logout")
def api_post():
    max_request_size = (
        MAX_BUILDER_REQUEST_SIZE
        if request.path == "/api/visualize-built"
        else MAX_REQUEST_SIZE
    )
    request_data, error_response = read_json_request(max_request_size)
    if error_response is not None:
        return error_response

    try:
        if request.path == "/api/account/register":
            return register_account(request_data)
        if request.path == "/api/account/login":
            return login_account(request_data)
        if request.path == "/api/account/logout":
            return logout_account()
        if request.path == "/api/visualize-built":
            return visualize_built_molecule(request_data)
        return do_molecule_search(request_data)
    except mysql.connector.Error as error:
        return send_mysql_error(error)


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/<path:filename>")
def static_file(filename):
    return send_from_directory(STATIC_DIR, filename)


@app.errorhandler(404)
@app.errorhandler(405)
def handle_not_found(error):
    if request.path.startswith("/api/") or request.method == "POST":
        return json_response(404, {"error": "API endpoint not found."})
    return error


def main():
    """Start the local Flask app on http://127.0.0.1:8000."""
    try:
        initialize_user_database()
    except mysql.connector.Error as error:
        raise SystemExit(
            "Could not connect to MySQL. Set MYSQL_HOST, MYSQL_PORT, "
            "MYSQL_DATABASE, MYSQL_USER, and MYSQL_PASSWORD. " + str(error)
        ) from error
    print("Molecule viewer ready at http://127.0.0.1:8000")
    try:
        app.run(host="127.0.0.1", port=8000, threaded=True)
    except KeyboardInterrupt:
        print("\nStopping molecule viewer.")
    finally:
        stop_vpython_viewer()


if __name__ == "__main__":
    main()
