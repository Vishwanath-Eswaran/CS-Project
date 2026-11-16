# VSEPR Molecule Viewer

## Project layout

```text
VSEPR/
|-- app.py                 # Local application launcher
|-- requirements.txt       # Python dependencies
|-- data/                  # Element table and saved molecule library
|-- docs/                  # Project overview and code walkthrough
|-- scripts/               # Molecule-library generator and CLI viewer
|-- static/                # Browser pages and assets
`-- vsepr/                 # Flask app, chemistry logic, and VPython renderer
```

## Run locally

Install the packages in `requirements.txt`, make sure MySQL is running, and
configure the `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER`, and
`MYSQL_PASSWORD` environment variables as needed. From this folder, run:

```powershell
python app.py
```

Then open `http://127.0.0.1:8000`. Press Ctrl+C to stop the server and its
VPython viewer.

To regenerate the starter molecule data, run:

```powershell
python -m scripts.populate_molecules
```

The command-line molecule viewer can be launched with
`python -m scripts.test [molecule-name-or-PubChem-CID]`.

For a plain-language project overview and a code walkthrough, see
[`docs/project_explanation.txt`](docs/project_explanation.txt) and
[`docs/project_line_by_line.txt`](docs/project_line_by_line.txt).
