# Sevah

Sevah is a small Python application that finds the five assisted-living
facilities nearest to a US ZIP code. The UI uses Streamlit, domain data is
validated with Pydantic, and the discovery workflow is orchestrated with
LangGraph.

When `GOOGLE_PLACES_API_KEY` is configured, Sevah requests live results from
Google Places API (New). When the key is absent or the live request fails, it
uses clearly labeled, bundled sample data. In both paths, Sevah resolves the
ZIP centroid offline, calculates straight-line Haversine distances, and sorts
the facilities from nearest to farthest.

## Requirements

- Python 3.10 or newer
- `pip`

## Setup

```bash
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS or Linux
source .venv/bin/activate
```

Install dependencies and create local configuration:

```bash
python -m pip install -r requirement.txt
cp .env.example .env
```

On Windows PowerShell, use `Copy-Item .env.example .env` instead of `cp`.

To use live data, set `GOOGLE_PLACES_API_KEY` in `.env` to a key whose Google
Cloud project has Places API (New) enabled. Leave it blank to use sample data.

## Run

```bash
streamlit run streamlit_app.py
```

Enter a five-digit US ZIP code. The result banner identifies the records as
either **Live Google Places data** or **Bundled sample data**.

## Test

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

On macOS or Linux, use `PYTHONPATH=src python -m unittest discover -s tests -v`.

## Project structure

```text
Sevah/
├── tests/
│   ├── test_discovery.py
│   ├── test_distance.py
│   ├── test_google_places.py
│   └── test_ui.py
├── src/
│   └── sevah/
│       ├── data/
│       │   └── facilities.json
│       ├── services/
│       │   ├── google_places.py
│       │   ├── sample_facilities.py
│       │   └── zip_codes.py
│       ├── __init__.py
│       ├── discovery.py
│       ├── distance.py
│       ├── models.py
│       └── ui.py
├── .env.example
├── .gitignore
├── requirement.txt
├── streamlit_app.py
└── README.md
```

## Sample data

The bundled records are fictional facilities intended only for development and
testing. They are not healthcare recommendations or an authoritative directory.

For a ZIP outside the Chicago area, sample facilities can be far away. This is
expected: the sample dataset is intentionally small, while distances are still
calculated from the entered ZIP code's actual approximate centroid.
