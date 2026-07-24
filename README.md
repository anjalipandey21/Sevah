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

## CMS enrichment MVP limitation

The enrichment layer uses the CMS **Nursing Home Provider Information** dataset
as a short-term proxy for assisted-living data. CMS records describe currently
active Medicare- or Medicaid-certified nursing homes. Assisted-living
facilities are a different category and may not be CMS-certified nursing homes,
so a valid discovery facility often will not have a CMS match. A missing match
must not be interpreted as a quality, certification, or eligibility signal.

CMS enrichment is intentionally separate from the current LangGraph and UI. The
`enrich_facilities_with_cms` service:

1. loads real CMS Provider Information candidates for the exact ZIP code;
2. compares normalized facility names using fuzzy matching;
3. requires a score of at least 90 and a five-point lead over the runner-up;
4. returns `matched=false` and no CMS attributes for weak or ambiguous matches.

Reliable matches include the CCN, certified bed count, overall rating, staffing
rating, ownership type, chain name, and match score. The separate ownership
adapter loads live CMS Ownership rows by CCN. Verified names, roles, owner
types, ownership percentages, and association dates are displayed when
available. If CMS cannot return records, production results are explicitly
`unavailable`; fictional sample ownership is available only through explicit
test injection and is never presented as verified management. CMS ownership
and management records are not necessarily a facility's complete current
executive leadership team.

### CMS ACO SNF affiliate enrichment

For a reliable provider match, Sevah checks the official CMS **Accountable Care
Organization Skilled Nursing Facility Affiliates** dataset. Affiliation can be
confirmed only by exact normalized CCN—never by a fuzzy facility-name match.
Results distinguish `confirmed`, `not_found`, `unavailable`, and
`not_applicable`.

The current official 2026 API response and data dictionary publish the SNF
affiliate legal business name (`Aff_LBN`) but no SNF CCN. Sevah therefore
reports ACO lookup as `unavailable` for this live version rather than inferring
affiliation by name. Its exact-CCN loader boundary supports a future official
CCN-bearing version and deterministic injected test rows. ALFs commonly lack a
CMS nursing-home match, and without a reliable CMS CCN their ACO result is
`not_applicable`.

The enrichment layer can be called after discovery without changing the
existing workflow:

```python
from sevah.cms_enrichment import enrich_discovery_result_with_cms
from sevah.discovery import discover_facilities

discovery = discover_facilities("60614")
cms_enrichment = enrich_discovery_result_with_cms(discovery)
```

## Deterministic robotics-affinity assessment

The robotics-affinity layer retrieves bounded visible text from a facility's
public website and extracts only configured service, technology, and marketing
phrases. It does not use an LLM or infer services that are not explicitly
mentioned. Website requests reject private and non-routable hosts, non-HTTP
URLs, non-HTML responses, and responses larger than 1 MB.

The explainable score is the sum of four capped components:

| Component | Maximum | Evidence |
| --- | ---: | --- |
| Service fit | 40 | Nursing, rehabilitation, therapy, memory-care, and related services |
| Technology readiness | 35 | Robotics, monitoring, telehealth, portals, smart technology, and related signals |
| Operating and partnership readiness | 15 | CMS beds (9), chain membership (3), and confirmed exact-CCN ACO affiliation (3) |
| Innovation marketing | 10 | Explicit innovation, technology-enabled, personalized-care, and independence language |

CMS overall and staffing ratings do not affect the score. Those are care
quality fields, not evidence of robotics readiness.

Confidence is separate from affinity. It reflects evidence completeness:
10 points for the structured facility record, 40–60 for retrievable website
content, and 30 for a reliable CMS match. Every result returns component
reasons, evidence labels, confidence reasons, and this limitation:

> The score is a prioritization heuristic—not a clinical-quality rating,
> procurement recommendation, or proof that robotics is appropriate.

```python
from sevah.robotics_affinity import analyze_robotics_affinity

assessment = analyze_robotics_affinity(
    facility,
    cms_enrichment=cms_match,
)
```

## Bounded technology research

The optional registered `technology_research` node inspects only the facility's
official website homepage and at most two additional same-origin pages.
Technology, innovation, services, telehealth, digital care, safety, and
resident-experience links are preferred. The existing SSRF checks, public-host
validation, HTML-only rule, request timeout, and 1 MB response limit apply to
every page. External domains, LinkedIn, and search engines are excluded.

Signals use the fixed deterministic technology taxonomy. Every new signal
includes its matched term and source URL. Research adds only the incremental
technology points up to the existing 35-point component cap. Prompt overrides
are stored as bounded research guidance and cannot change page limits, allowed
origins, network protections, taxonomy, or score caps.

## Safe Agent Harness

`safe_feedback.py` is a constrained agent harness, not a general autonomous
agent and not an arbitrary-code executor. It accepts typed human feedback,
validates nodes and services against allowlists, stores `GraphSpec`, applies
registered prompt overrides, rebuilds legal graph paths, and runs deterministic
scoring.

One atomic **Enable technology research** action:

1. enables the optional registered node;
2. changes `positioning → scope → scoring` to
   `positioning → technology_research → scope → scoring`;
3. stores the node's editable prompt override;
4. rebuilds the next evaluation graph; and
5. increments the graph revision exactly once.

The Streamlit graph-evolution view shows the revision, enabled nodes, active
path, prompt overrides, and executed nodes. Product-side human review remains
mandatory through LangGraph interrupt/resume. The application displays source
evidence, matched terms, score rules and components, confidence reasons,
corrections, previous and revised scores, executed paths, and concise decision
summaries. It does not expose or claim to record private chain-of-thought.

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
either **Live Google Places data** or **Bundled sample data**. The completed UI
also displays CMS and ACO states, verified management records, affinity
components and confidence, the Safe Agent Harness, graph revision and path,
sourced technology research, and human review approval or rejection with
interrupt/resume support.

## Assessment recording checklist

1. Start an external screen recording.
2. Explain the architecture.
3. Search a ZIP code.
4. Show facility, CMS, management, ACO, services, and marketing evidence.
5. Explain the deterministic score.
6. Submit human feedback enabling technology research.
7. Show the new node, route, prompt, evidence, and revised score.
8. Approve or reject the final result.

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
│   ├── test_robotics_affinity.py
│   ├── test_cms_aco.py
│   ├── test_technology_research.py
│   ├── test_service_marketing.py
│   ├── test_cms_api.py
│   ├── test_cms_enrichment.py
│   ├── test_discovery.py
│   ├── test_distance.py
│   ├── test_google_places.py
│   ├── test_ownership.py
│   ├── test_website_content.py
│   └── test_ui.py
├── src/
│   └── sevah/
│       ├── data/
│       │   ├── facilities.json
│       │   └── sample_ownership.json
│       ├── services/
│       │   ├── cms_api.py
│       │   ├── cms_aco.py
│       │   ├── google_places.py
│       │   ├── ownership.py
│       │   ├── sample_facilities.py
│       │   ├── website_content.py
│       │   ├── technology_research.py
│       │   └── zip_codes.py
│       ├── __init__.py
│       ├── affinity_models.py
│       ├── cms_enrichment.py
│       ├── cms_models.py
│       ├── discovery.py
│       ├── distance.py
│       ├── models.py
│       ├── robotics_affinity.py
│       ├── service_marketing.py
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
