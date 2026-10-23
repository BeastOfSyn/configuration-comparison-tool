# Configuration Comparison Tool
## Architecture, Technical Design & Future Scope

**Author:** BeastOfSyn
**Version:** 12.3

---

## 1. Executive Summary & Problem Statement

### 1.1 The Problem

In enterprise CRM ecosystems, configuration rules (PMR - Process Management
Rules, Alert Rules, and Business Processes) dictate critical workflow routing,
field-level validations, SLA triggers, and business logic. During multi-environment
promotion cycles (**DEV → Staging → PROD**), configurations are frequently
modified, updated, or backported.

### 1.2 Why Traditional Tools Fail

Standard comparison tools (WinMerge, Beyond Compare, Git Diff, plain Excel
formulas) fall short for enterprise CRM audits because:

1. **XML/JSON Serialization Jitter**: XML attributes or condition nodes often
   reorder during database exports (e.g., `<cond field="A" op="eq"/>` vs
   `<cond op="eq" field="A"/>`), triggering massive false positives in text diffing.
2. **Type Coercion & Float Inconsistencies**: Excel exports frequently convert
   integer IDs to floats (`101` → `101.0`), insert trailing decimals into
   scientific notation (`1.2345e+42`), or reformat dates with arbitrary
   timestamps (`2024-01-01 00:00:00.000`).
3. **Composite Primary Keys**: Many entities do not use a single ID column;
   they depend on composite keys like `(OwnerId, RuleId)` or `(OwnerID, ProcessID)`.
4. **Data Quality / Corruption Masking**: Truncated XML blobs or corrupt values
   can slip through unnoticed or crash naive diff scripts.
5. **Audit Trail vs Functional Logic Confusion**: A record modified by an admin
   timestamp change (`LastModifiedOn`) is an *audit update*, not a *functional
   logic change*. Traditional diffs treat both identically.

### 1.3 The Solution

The **Configuration Comparison Tool** is a purpose-built, deterministic,
AST-aware diffing engine coupled with a lightweight FastAPI backend and
high-performance desktop web interface. It parses, normalizes, inspects, and
diffs complex CRM configurations with sub-second latency, zero cloud
dependencies, and zero risk of data leakage.

```
+---------------------------------------------------------------------------------------+
|                                  WORKFLOW                                             |
|                                                                                       |
|   +-----------------------+                    +-----------------------+              |
|   |   DEV Environment     |                    |   PROD Environment    |              |
|   |   Baseline Export     |                    |   Audited Export      |              |
|   +-----------+-----------+                    +-----------+-----------+              |
|               |                                            |                          |
|               +--------------------+  +--------------------+                          |
|                                    |  |                                               |
|                                    v  v                                               |
|                       +----------------------------+                                  |
|                       |  FastAPI Streaming Ingest  |                                  |
|                       +--------------+-------------+                                  |
|                                      |                                                |
|                                      v                                                |
|                       +----------------------------+                                  |
|                       |    Engine Normalization    |                                  |
|                       |  - Column Aliasing         |                                  |
|                       |  - Float / Type Cleaning   |                                  |
|                       |  - XML AST Canonicalizer   |                                  |
|                       |  - JSON Sorter & Sanitizer |                                  |
|                       |  - Composite Key Matcher   |                                  |
|                       +--------------+-------------+                                  |
|                                      |                                                |
|                                      v                                                |
|                       +----------------------------+                                  |
|                       | Semantic Verdict Engine    |                                  |
|                       |  - Functional Diffs        |                                  |
|                       |  - Added / Removed in PROD |                                  |
|                       |  - Data Quality Anomalies  |                                  |
|                       |  - Audit-Only Segregation  |                                  |
|                       +--------------+-------------+                                  |
|                                      |                                                |
|                                      v                                                |
|                       +----------------------------+                                  |
|                       |  Fast Responsive UI (SPA)  |                                  |
|                       |  - LCS Token Diffing       |                                  |
|                       |  - Keyboard Nav (Up/Down)  |                                  |
|                       |  - Multi-module In-Memory  |                                  |
|                       +----------------------------+                                  |
+---------------------------------------------------------------------------------------+
```

---

## 2. End-to-End System Architecture & Codebase Walkthrough

```
Configuration_Comparison_Tool/
├── engine.py                  # Core Diffing, AST Canonicalization & DQ Engine
├── app.py                     # FastAPI ASGI Server & Multi-part File Endpoints
├── main.py                    # Standalone Desktop Bootstrap & Browser Launcher
├── PMR_Comparison.spec        # PyInstaller Spec for Frozen Bundling
├── build.bat                  # Automated 1-Click Environment Setup & Packaging
├── static/
│   └── index.html             # Embedded UI (Vanilla CSS + HTML5 + ES6 JavaScript)
├── test_data/                 # Synthetic Excel test suites (PMR, Alert, Process)
├── test_exe_endpoints.py      # Automated End-to-End API Integration Suite
└── validate_build.py          # Static Code Quality & Build Verification Hook
```

---

### 2.1 `engine.py` — The Core Semantic Diff Engine

`engine.py` represents the analytical backbone of the tool. It is split into 5 distinct pipeline layers:

#### A. Schema Configuration Layer (`TableConfig`)
Each module's configuration schema is declared declaratively via `TableConfig`:
- **`key`**: Primary key components (e.g., `("OwnerId", "RuleId")` for Alert Rule, `("RuleID",)` for PMR).
- **`functional`**: High-priority business logic columns (e.g., `FilterExpression`, `MappingXML`, `GeographyMappingFields`).
- **`xml_fields`**: Columns treated as XML syntax and parsed into ElementTrees.
- **`json_fields`**: Columns parsed as JSON trees.
- **`scalar`**: Simple value fields (e.g., `FieldColorMapping`, `FiredOption`).
- **`audit`**: Metadata columns tracked separately (`LastModifiedBy`, `LastModifiedOn`).
- **`aliases`**: Mapping legacy/variant Excel headers to canonical names.

#### B. Header & Column Normalization (`_resolve_columns`)
- Performs case-insensitive, whitespace-trimmed matching.
- Resolves schema aliases before canonical column alignment.
- Handles edge cases where both canonical and alias names are present in the
  same workbook, preventing duplicate column collisions.

#### C. Type & Value Sanitization
- **`clean_scalar(v)`**: Cleans NaN floats, converts whole floats (`12.0`) to
  canonical integers (`12`), strips whitespace.
- **`normalize_list(v)`**: Splits comma-separated values, removes time
  components from date-stamps (`12/05/2024 00:00:00` → `12/05/2024`), and
  sorts tokens numerically/alphabetically so that `"10, 20, 5"` matches
  `"5, 10, 20"`.

#### D. AST-Level Canonicalization (`canonical_xml` & `compare_xml`)
- **Node & Attribute Sorting**: Attributes of every XML element are sorted alphabetically.
- **Expression Signature Sorting**: Under `<FilterExpression>` or
  `<FilterCondition>`, condition nodes are sorted by an invariant signature
  `(tag, fieldname, op, normalized_values)`. If two environments have the
  exact same filter rules in different XML tag order, the engine recognises
  them as mathematically equivalent (0 false positives).
- **Sub-element Diffing**: For modified XMLs, condition lists are set-diffed
  to produce structured diff details:
  - `+ Condition Added to PROD`
  - `− Condition Removed from PROD`
  - `~ Operator Changed in PROD (e.g., Equals → GreaterThan)`
  - `~ Value Modified in PROD`

#### E. Data Quality (DQ) Pipeline
- Identifies unparseable XML syntax (`<Bad XML`), missing keys, corrupted JSON
  schemas, or anomalous data before diffing.
- Quarantines DQ rows into a dedicated **DATA QUALITY** bucket with exact
  error causes while preserving raw payloads for remediation.

---

### 2.2 `app.py` — High-Throughput REST API

- Built using **FastAPI** on **Starlette/Uvicorn**.
- Provides `/api/modules`, `/api/health`, and `/api/compare/{module}`.
- Handles multipart Excel uploads (`.xlsx`, `.xls`) asynchronously.
- Directs file byte streams to temporary storage, invokes `compare_files()`,
  and cleans up files in a `finally` block to prevent disk bloat.
- Solves path resolution dynamically: when frozen in PyInstaller
  (`sys._MEIPASS`), it reads assets from the runtime bundle directory; when
  running in development, it reads from the workspace root.

---

### 2.3 `main.py` & `build.bat` — Desktop Portability

- **`multiprocessing.freeze_support()`**: Ensures Windows process spawning
  does not recurse when packaged into a single binary.
- **Auto-Browser Dispatch**: Launches a daemon thread that polls server
  readiness and automatically opens `http://127.0.0.1:8000` in the user's
  default browser.
- **`build.bat`**: Creates an isolated `.buildenv` virtual environment,
  installs dependencies, verifies static integrity, and compiles
  `dist\Configuration_Comparison_Tool.exe` with PyInstaller in a single click.

---

### 2.4 `static/index.html` — Zero-Dependency UI

- **Single-File Architecture**: HTML5, CSS tokens, and ES6 JavaScript packed
  in a single file for instantaneous offline execution.
- **In-Memory Multi-Module Isolation**:
  State (`devFile`, `prodFile`, `result`, `filter`, `search`, `selected`) is
  preserved per module in memory. Tab switching between PMR, Alert Rule, and
  Process is instantaneous without re-uploading or losing active rule selections.
- **Race-Condition Protected Async Engine**: Comparison requests are scoped to
  their initiating module ID; switching modules while a diff is calculating
  will never trigger ghost popups or overwrite active screens.
- **LCS Token Diff Engine (`diffTokenSeq`)**:
  Implements dynamic programming (DP) Longest Common Subsequence token diffing
  inside the browser. Highlights exact character/word additions
  (`<mark class="diff-add">`) and deletions (`<mark class="diff-del">`) inside
  massive XML strings without requiring external libraries.
- **High-Velocity Keyboard Subsystem**:
  - ↑/↓: Navigate smoothly across rules in the active list.
  - ←/→: Cycle filter chips (`MODIFIED` → `ADDED` → `REMOVED` →
    `AUDIT-ONLY` → `DATA QUALITY` → `ALL`).
  - `Tab / Shift+Tab`: Switch between modules (PMR, Alert Rule, Process).
  - `Home / End`: Jump directly to start/end of rule explorer.

---

## 3. Technical Q&A

### Q1: Why build a custom diff tool instead of using Beyond Compare, Excel formulas, or Git?

> Configuration payloads are deeply structured XML expressions, JSON metadata,
> and comma-delimited lists. Database dumps frequently change attribute order or
> XML node order, which creates hundreds of false-positive diffs in WinMerge/Git.
> Excel often introduces numeric artifacts (e.g., float formatting `101.0` vs
> `101`). Business logic is keyed by composite identifiers (e.g. `OwnerID +
> RuleID`), whereas row numbers in Excel exports fluctuate whenever new rules
> are added. This tool performs semantic AST normalization: it parses the
> XML/JSON trees, sorts nodes canonically, extracts individual condition changes,
> isolates audit updates from logic updates, and eliminates 100% of formatting
> noise.

---

### Q2: How does the engine differentiate between an "Audit Update" and a "Functional Logic Change"?

> In `engine.py`, columns are categorized into `functional` (e.g.,
> `FilterExpression`, `MappingXML`, `FieldColorMapping`) and `audit`
> (`LastModifiedBy`, `LastModifiedOn`).
> - If any `functional` or auto-detected business columns change, the rule is
>   classified as **`MODIFIED IN PROD`**.
> - If only `LastModifiedBy` or `LastModifiedOn` changed while all functional
>   payloads remain identical, the engine marks the record as **`AUDIT-ONLY`**
>   (`audit_only = True`).
> This allows auditors to immediately focus on logic changes that impact
> production behavior rather than administrative touch timestamps.

---

### Q3: What is the significance of the "OwnerID 477" handling?

> `OwnerID = 477` is a system-default / administrative owner identifier. In
> previous versions, showing 'Owner 477' across hundreds of rules cluttered the
> UI. In our architecture:
> 1. The record itself is **never omitted** or dropped from comparison.
> 2. The primary key composite integrity is strictly maintained for matching.
> 3. In the UI display layer, `OwnerID 477` is gracefully masked from badge tags
>    so users see the clean `RuleID` or `ProcessID` without distracting system IDs.

---

### Q4: How do you handle schema variations and column header mismatches?

> A 2-stage column resolution pipeline in `_resolve_columns`:
> 1. **Case-Insensitive & Whitespace Trimming**: Headers like `OwnerId`,
>    `OwnerID`, `ownerid `, or `Rule_ID` are canonicalized.
> 2. **Configured Aliases**: Known legacy aliases are resolved using alias lookup
>    tables with duplicate-target collision protection.
> 3. **Unconfigured Column Drift Detection**: Beyond declared fields, `_diff_fields`
>    automatically detects any shared columns present in both DEV and PROD and
>    diffs them as scalar values, ensuring unexpected column additions/changes
>    are never missed.

---

### Q5: How does the tool guarantee high performance on large sheets (3,500+ rules)?

> 1. **Pandas Vectorized Pre-processing & Dictionary Indexing**: Ingestion and
>    column normalization are vectorized; row pairing is done via dictionary
>    lookups on normalized key tuples (O(N) matching instead of O(N²) nested scanning).
> 2. **Short-Circuit Equality**: Before doing deep XML/JSON tree parsing, fast
>    scalar string equality and hash checks skip unchanged payloads in microseconds.
> 3. **Client-Side Virtualized & Optimized DOM**: The frontend uses lightweight
>    vanilla DOM manipulation with native scrolling and localized DP string
>    diffing capped at 4,000 tokens to ensure zero UI freezing.

---

### Q6: How does the UI handle multi-module state and asynchronous comparisons?

> The UI maintains a dedicated in-memory state object for each module (`pmr`,
> `alert_rule`, `process`). Each comparison request locks its initiating module
> ID. If an auditor initiates a PMR diff and immediately switches to Alert Rule,
> the incoming PMR result is saved directly into `state['pmr'].result` in the
> background and will NOT disrupt the active Alert Rule screen. When switching
> back to PMR, the loaded results and filter state are instantly restored without
> re-querying.

---

### Q7: Why is the solution packaged as a standalone EXE, and how is security ensured?

> Corporate and enterprise environments often have strict restrictions on Python
> runtimes, Node.js installations, or external cloud uploads.
> 1. **Hermetic Standalone Packaging**: PyInstaller packages Python 3.12,
>    Uvicorn, FastAPI, Pandas, and OpenPyXL into a single self-contained binary.
> 2. **Zero Data Exfiltration**: The application runs strictly on `127.0.0.1`
>    (localhost). No data ever leaves the local machine.
> 3. **Automatic Lifecycle Cleanup**: Uploaded files are streamed to temporary
>    storage, parsed in memory, and immediately unlinked/deleted upon request
>    completion.

---

## 4. Future Scope

### 4.1 Auto-Collection via Power Automate & Direct Integration

Currently, users manually upload Excel sheets. In a future phase, this workflow
can be 100% automated:
- **Scheduled flows** run daily, executing database extraction or OData/REST API
  queries against DEV and PROD environments.
- **Automated headless diff trigger**: a webhook or CLI call triggers the diff
  engine and compares yesterday's baseline vs today's snapshot.

### 4.2 Generic Schema Registry (Scaling to All CRM Tables)

Currently, schemas are declared in `TABLE_CONFIGS` for PMR, Alert Rule, and
Process. Expanding to an external **Schema Registry** (YAML/JSON) allows
zero-code extensibility:

```yaml
# config_schemas/lead_routing.yaml
module_name: lead_routing
display_label: "Lead Routing Matrix"
primary_key: ["TerritoryID", "ProductCode"]
functional_fields:
  - name: "AssignmentXML"
    type: "xml"
  - name: "SLA_Hours"
    type: "scalar"
audit_fields: ["UpdatedBy", "UpdatedOn"]
```

Adding a new configuration table requires simply dropping a YAML schema into
the folder without altering core Python logic.

### 4.3 AI/ML-Powered Heuristic Drift & Risk Classification

Not all configuration differences have the same blast radius:
- **Low Risk**: Changing a display label from "Customer ID" to "Client ID".
- **Critical Risk**: Removing a validation rule that enforces PAN/SSN checks,
  or widening a routing condition from `<Amount gt="100000">` to
  `<Amount gt="0">`.

Roadmap:
1. **Semantic Impact Vectorization**: Tokenize rule changes and pass them
   through a lightweight embedding model to compute semantic change magnitude.
2. **Risk Scoring Model**: Classifies diffs into `CRITICAL`, `WARNING`, and
   `ROUTINE`. Identifies rogue changes made directly in PROD that never
   originated in DEV.
3. **Historical Pattern Training**: Model learns historical change approval logs
   to predict whether a configuration change is likely to cause downstream
   production incidents.

### 4.4 Automated CI/CD Governance

- Plug the engine into **Azure DevOps / Jenkins / GitHub Actions**.
- When a sprint release is ready for PROD deployment, the pipeline automatically
  diffs DEV configuration against current PROD.
- If unexpected or unapproved configuration diffs exist, the pipeline
  automatically halts and requires senior architect sign-off.

---

## 5. Comparison Summary

| Dimension | Legacy / Manual Process | Configuration Comparison Tool |
|---|---|---|
| **Diff Accuracy** | High false-positive rate due to XML/JSON ordering & float formatting | **100% Deterministic Semantic AST diffing** |
| **Audit Differentiation** | Treats admin timestamps as full logic changes | **Separates Functional logic from Audit metadata** |
| **Data Quality** | Crashes on corrupt XML or silently skips corrupted rows | **Dedicated Data Quality quarantine with exact cause reporting** |
| **Security & Privacy** | Requires cloud services or manual copy-pasting | **100% Localhost, zero exfiltration, standalone EXE** |
| **Auditor Speed** | Hours of manual spreadsheet VLOOKUPs | **Sub-second comparison with full keyboard navigation** |
| **Future Readiness** | Hardcoded, manual file downloads | **Extensible to all tables, automated ingest & ML risk scoring** |
