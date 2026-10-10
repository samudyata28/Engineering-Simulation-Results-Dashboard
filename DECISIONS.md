# Decisions, assumptions and open questions

## 1. Assumptions (made where domain knowledge was missing)

| # | Assumption | Consequence if wrong |
|---|---|---|
| A1 | In the supplied data a CSV name is both the **component** and the **project** (Bracket, Housing, Lens). They are one table (`projects`); the API/UI show both labels. | Add a `components` table under `projects`; demands already reference `project_id` only. |
| A2 | Each CSV is a single-curve frequency-response of **displacement magnitude** (an amplitude), so it is never negative; negative values are rejected as corrupt. | Relax the validator. |
| A3 | Revision order is the **natural sort of the folder name** (`rev2 < rev10`). "Latest" = last in that order. | Add a revision-date/metadata file. |
| A4 | The 15 mm / 0–50 Hz rule applies to every component. The inclusive bounds and `≤ 15` are applied exactly (15.0 passes, 15.01 fails, 50.0 Hz included, 50.1 Hz excluded). Floating-point compares are exact on the CSV values. | Per-component criteria: move `Criteria` into a table keyed by project. |
| A5 | The in-range **peak is the max of the sampled points**; no curve fitting between samples. | See "marginal" below and question Q1. |
| A6 | "Unchanged" means a peak change ≤ 0.05 mm (half of the 0.1 mm CSV resolution). Lower magnitude = improved. | Configurable in `Criteria.change_tolerance`. |
| A7 | An invalid row rejects the **whole file**. Dropping a bad row could silently drop the peak, giving a misleading pass. | — |
| A8 | If the data stops before 50 Hz with no violation, the result is **Inconclusive**, not Pass. If there are no samples in range it is **Not assessable**. A violation is still a Fail even with incomplete coverage. | — |

## 2. Things the data revealed (and how the app treats them)

* **Sparse, non-identical frequency grids.** Revisions are sampled at slightly different frequencies (e.g. Bracket's peak sample is
  37.6 Hz in rev1 and 37.8 Hz in rev2; Lens rev1 has an extra 36.8 Hz sample). Consecutive samples around the resonance are ~2 Hz
  apart, while the resonance is narrow. A true peak could sit between samples and exceed the limit.
  → Passes with less than 10 % of the limit as margin are labelled **“Pass · marginal”** (amber, `!`) with an explanation. Today that
  is Housing rev2 (14.9 mm, 0.1 mm margin), Housing rev3 (14.2) and Bracket rev3 (13.8). The result is still a pass per the stated
  rule; the UI just refuses to over-claim.
* **Comparing curves on different grids** needs interpolation. The Δ-curve uses linear interpolation on the union grid over the
  overlap and says so on screen; headline metrics (peak, peak frequency, margin) never use interpolation.
* **Trend can hide a reversal.** Lens improves 18.0 → 17.5 from rev1 to rev3 but regressed 16.1 → 17.5 in the last step. The history
  text and overview show both "vs previous" and "vs first" so neither is hidden.
* **No data between 0 and 5 Hz.** Shown as an info note (the range is assessed over available samples).
* **A passing result does not close a demand.** Bracket and Housing now pass in rev3 but their demands stay **Open** and are flagged
  *"latest result passes — review whether this can be resolved"*. Conversely a Resolved demand whose latest result fails again is flagged *regressed*.

## 3. Data model

`projects 1─* results *─1 revisions`, `results 1─* samples`, `projects 1─* demands → origin result`, plus `import_runs/import_issues` and `demand_events`.

* A **result** is one component in one revision. It stores file provenance (relative path, SHA-256, mtime, `data_version`) and the
  **calculated summary** (peak, frequency, margin, status, warnings, and the criterion it was calculated with). Summaries are
  persisted so list/overview endpoints don't re-scan samples, and they are **recomputed automatically from stored samples if the
  configured criterion changes** (tested).
* A **demand** stores its *origin snapshot* (revision, metric, value, frequency, limit, range) frozen at creation, plus an FK to
  the origin result. Per-revision results are **derived at read time** by joining on the project, not copied. That is what makes one
  rev1 demand automatically "follow" the component into rev2, rev3 and any future revision with no replacement demands. If the
  origin CSV is later re-imported with different numbers, the demand keeps what the engineer originally saw and shows a *drift* warning.
* `demand_events` is an append-only audit log (created / status change / description edit). There are no users yet, so no actor column.
* **Why SQLite:** zero-ops, single file, transactional (a changed file is replaced atomically), plenty for ~10⁵ rows, ships with Python,
  easy to inspect and to commit as a fixture. Everything goes through SQLAlchemy 2.0 so Postgres is a one-line URL change; the only
  SQLite-specific code is the PRAGMA hook. I did **not** add Alembic for the MVP (`create_all`); it would be the first thing to add
  before any schema change in a deployed instance.

## 4. Ingestion design

Idempotency key = *(revision folder, project name)* + content hash. Per-file savepoints isolate failures. Rejections are reported
(CLI exit code, `import_issues`, Overview panel). Considered and rejected: a filesystem watcher (more moving parts, platform quirks; the
explicit Sync button + start-up import is predictable and testable), and importing lazily on request (hides failures from the reader).
Files are hashed, not trusted by mtime, so a `touch` or a copy doesn't cause a re-import and a same-mtime edit isn't missed.

## 5. API/UI/chart choices

* **Layers:** `parsing`/`metrics` are pure (unit-tested without DB or HTTP); `discovery` knows only the filesystem; `importer` is the only
  writer of results; `views` shapes responses; `routes` is thin. The frontend only talks to `/api` through one typed client (`api.ts`).
* **Chart:** line + markers on a *linear* frequency axis 0–200 Hz (the data is sparse and the story is a single resonance below 50 Hz).
  The assessed range is a shaded band, the limit a dashed red line (labelled with value and unit), and the peak a ringed marker with a
  direct label "19.9 mm @ 37.6 Hz". A *Zoom to assessed range* toggle resolves the resonance; the default shows the full response because
  the brief wants >50 Hz visible. Compare view overlays base (grey dashed) and target (blue) and adds a Δ-curve below it.
* **Colour is never the only signal:** every status has an icon and a word (✓ Pass, ! Pass · marginal, ✕ Fail, ? Inconclusive), changes use ▼/▲/=,
  and the chart marks are labelled. Light and dark themes are supported.
* **Wording:** verdict sentences state the numbers, the range and the limit ("peak 19.9 mm at 37.6 Hz (within 0–50 Hz) exceeds the
  15 mm limit by 4.90 mm"). The footer and criteria text repeat that this is a data-review criterion only.
* **Alternatives considered:** Plotly/ECharts (heavier bundle, less control over annotations) vs **Recharts** (small, React-native, enough);
  log-frequency axis (rejected: grid is linear and 0 Hz can't be shown); small-multiples per revision (rejected: overlay makes shifts visible);
  server-side pre-rendered images (rejected: no hover/interactivity). Redux/React-Query (rejected: a 20-line `useAsync` hook is enough).

## 6. Known limitations / future improvements

* Authentication, user identity on demand events, comments, assignees and due dates.
* Alembic migrations; Postgres; background import with progress; file-watcher or webhook trigger.
* Per-component criteria and multiple criteria (e.g. several metrics/frequency bands) – the `Criteria` object and `criteria_key`
  recompute path are already the seam for this.
* Peak refinement: quadratic/spline interpolation or a request for finer frequency resolution near resonances; automatic detection of
  multiple peaks and of peak-frequency shift (rev1→rev2 shift of 0.2 Hz is shown but not alerted on).
* Compare more than two revisions at once; export (CSV/PDF report) of a comparison; deep-linking charts to a frequency.
* Frontend component tests and an e2e (Playwright) smoke test; the backend has 56 tests, the frontend only helper tests.
* Pagination for demands and sample downsampling for very large curves.
* Single-process serving of the built SPA is for convenience; behind a real deployment use a CDN/reverse proxy.

## 7. Questions for an engineering domain expert

1. **Is the CSV a harmonic-response amplitude** (peak) or an RMS/other measure, at what excitation level, and does the 15 mm limit refer to the same quantity?
2. Is the **frequency resolution adequate**? With ~2 Hz spacing around a narrow resonance, how much could the true peak exceed the sampled peak? Should marginal passes need a refined run?
3. Should the margin threshold for "marginal" be 10 % of the limit, an absolute value, or tied to simulation uncertainty?
4. Is **peak frequency shift** (37.6 → 37.8 Hz) meaningful on its own (stiffness/mass change)? Should a shift towards the 50 Hz boundary raise an alert?
5. Why does Bracket **degrade in rev2 then recover in rev3** and Lens regress in rev3 — should the app record the design change per revision (notes/links to CAD) to explain it?
6. Does the same 15 mm / 0–50 Hz criterion apply to every component, or should limits and ranges be per component / load case?
7. What does **“unchanged”** mean physically: is 0.05 mm, or a percentage, the right tolerance?
8. Are **project** and **component** distinct in your organisation (e.g. a project containing several components)? How are revisions ordered when names are not `revN`?
9. Who may **resolve** a demand, and is a human sign-off/comment required (and should a second failing revision automatically re-open it)?
10. Are there data below 5 Hz that matter (e.g. static deflection at 0 Hz) since the criterion starts at 0 Hz?
