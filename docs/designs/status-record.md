# Status Record migration plan

Branch: `enh-statusrec-class`

Goal: replace the ad-hoc `dict` produced by `datalad.interface.results.get_status_dict`
with a typed dataclass-style class, **without breaking** any of the dict-shaped
consumers (in-tree code, JSON output, user hooks, third-party renderers), and
**with the smallest possible diff** so the change can be reviewed by a human in one
sitting.

## Guiding principle: small, reviewable v1 — but v2 is where the design is validated

A v1 PR should add the new class, route `get_status_dict` through it, and ship.
That PR alone is review-friendly: one new class + tests, no churn elsewhere.
But v1 in isolation is not *useful* — it does not yet exercise the design
choices (which fields are typed, which clusters deserve subclasses, whether
`extras` is comfortable, whether validation can be turned on). Those answers
come from v2, which is **planned and committed-to up front**, not deferred
indefinitely.

The four items below are **explicit non-goals for v1 and explicit goals for
v2**. They are the most interesting part of the migration because they are
how we discover the variability the v1 class must accommodate:

- Rewriting manual `dict(res_kwargs, status=..., ...)` spread sites.
- Converting `res['k']` / `res.get('k')` to attribute access in central
  consumers.
- Introducing action-specific subclasses where (and only where) the data
  warrants them.
- Adding validation, deprecation warnings, or strict modes.

v1 also does not retype existing function signatures or rename
`get_status_dict`; those are follow-ups (v2.5 / Phase 3).

What changes externally in v1 is approximately one line: `get_status_dict`
now returns a `StatusRecord` instead of a `dict`. Everything else that the
result moves through must be unchanged or test-equivalent. v2 then probes
the rest of the codebase to assess and shape the typed surface.

## 1. What we are migrating

The "result record" is the unit of data flow in DataLad. Every interface function
yields a stream of these. Today they are plain `dict`s, conventionally produced by
`get_status_dict` (`datalad/interface/results.py:61`).

Documented schema: `docs/source/design/result_records.rst` — defines mandatory
keys (`action`, `path`, `status`) and optional ones (`type`, `message`, `logger`,
`refds`, `parentds`, `state`, `error_message`, `exception`, `exception_traceback`,
`bytesize`, `gitshasum`, `prev_gitshasum`, `key`).

Surface area (from audit):

- **~140 call sites** of `get_status_dict` across **29 files** (mostly under
  `datalad/core/`, `datalad/distribution/`, `datalad/distributed/`,
  `datalad/local/`).
- **Manual dict-spread construction** that bypasses the helper:
  - `datalad/core/local/status.py:188-194,420-424`
  - `datalad/core/distributed/push.py:216-224`
  - `datalad/distribution/siblings.py:599-603,770-773`
  - `datalad/core/local/save.py:374-380`
  - `datalad/local/addurls.py:930-951`
- **Post-construction mutation** is widespread: `res['status'] = ...`,
  `res['message'] = ...`, `res['error_message'] = ...`, `res['path'] = ...`,
  `res['annex-ignore'] = 'false'` (`create_sibling_gin.py:172`), etc. The class
  must support `__setitem__`.
- `annexjson2result` (`datalad/interface/results.py:257`) builds a record then
  rewrites status, path, action, annexkey, metadata, error_message, message in
  place.

## 2. Backward-compat surface — non-negotiable

These usage patterns must keep working **unchanged**:

| Pattern | Where | Notes |
|---|---|---|
| `res['key']`, `res.get('key', dflt)` | everywhere | dict-style access |
| `'key' in res` | everywhere | membership |
| `res['key'] = v` | mutation sites listed above | post-construction edits |
| `res.pop('logger', None)` | `interface/utils.py:336` | strips logger before render/JSON |
| `dict(other_kwargs, status=..., ...)` spread | siblings.py, push.py, save.py, addurls.py | left as-is in v1 |
| `{k: v for k, v in res.items() if k in {...}}` | `interface/utils.py:411`, `_render_result_json` | iteration + items() |
| `json.dumps(...)` | `_render_result_json:432` | byte-for-byte equivalence required |
| `res == other_dict` | repetition detection | equality with plain dicts |
| `EnsureKeyChoice('action', ...)(res)` | `cli/exec.py`, `core/distributed/clone.py:140`, `core/local/create.py:104`, `distribution/install.py:111` | `__contains__` + `__getitem__` |
| `match_jsonhook2result(res, match)` | `core/local/resulthooks.py:79` | user-defined match dicts; arbitrary keys |
| `result_filter=lambda x: x.get('type') in (...)` | `core/local/run.py:549` | user-supplied callables |
| `res['message'][0] % res['message'][1:]` | `interface/utils.py:249` | message tuple shape preserved |
| arbitrary user `result_renderer` callables | extension API | treats `res` as dict — must remain dict-like |
| pickling across multiprocessing | `runnerthreads`, parallel get/clone | dataclass needs to be picklable |

`docs/source/design/result_records.rst` explicitly warns that **changing field
names breaks user hooks**. Therefore: same key names, same value shapes, same
JSON output, byte-for-byte where possible.

## 3. Design — `StatusRecord`

A `@dataclass`-based class that **also implements `MutableMapping`**, so every
existing consumer keeps working through dict semantics while new code can
opt-in to typed attribute access **in follow-up PRs**.

```python
# datalad/interface/results.py — added near get_status_dict

from collections.abc import MutableMapping
from dataclasses import dataclass, field, fields
from typing import Any, Optional, Union
import logging

from datalad.support.exceptions import CapturedException

MessageT = Union[str, tuple, None]


@dataclass
class StatusRecord(MutableMapping):
    """Typed result record yielded by DataLad interface functions.

    Behaves as both a dataclass (typed attribute access) and a
    MutableMapping (dict-style access for backward compatibility).
    Unknown / domain-specific keys are stored in ``extras``.
    """

    # mandatory per docs/source/design/result_records.rst
    # (kept Optional because get_status_dict allows None today)
    action: Optional[str] = None
    path:   Optional[str] = None
    status: Optional[str] = None

    # common optional
    type:                Optional[str] = None
    message:             MessageT = None
    logger:              Optional[logging.Logger] = None
    refds:               Optional[str] = None
    parentds:            Optional[str] = None
    state:               Optional[str] = None
    error_message:       MessageT = None
    exception:           Optional[Union[Exception, CapturedException]] = None
    exception_traceback: Optional[str] = None
    exit_code:           Optional[int] = None

    # escape hatch for action-specific keys
    extras: dict = field(default_factory=dict)

    # MutableMapping protocol — see implementation sketch in §3.2
    ...
```

### 3.1 Key design decisions

1. **All currently-documented fields are `Optional` and default to `None`.**
   Today `get_status_dict` only adds keys when given a non-None value. The
   Mapping protocol mirrors that: `__contains__` returns False for keys whose
   attribute is still `None`, `__iter__` skips them, `len()` counts only set
   keys. The *visible* dict contents are unchanged.
2. **`extras: dict`** captures the long tail of action-specific keys
   (`name`, `url`, `ssh_url`, `annex-ignore`, `bytesize`, `gitshasum`,
   `prev_gitshasum`, `key`, `annexkey`, `metadata`, `hints`, `stdout`, `stderr`,
   `stdout_json`, `branch`, `source_url`, `git`, `request_data`, `clone_url`,
   `destination`, `contains`, ...). These are *not* promoted to typed fields in
   v1 — there are too many, most are used by exactly one command, and adding
   them inflates the diff.
3. **No validation, no warnings, no deprecations in v1.** Schema today is
   "anything goes"; introducing strict checks alongside a class swap doubles
   migration risk.
4. **`get_status_dict()` keeps its signature.** Only its return type changes
   from `dict[str, Any]` to `StatusRecord`. All ~140 callers are untouched.
5. **No subclasses in v1.** `FileStatusRecord` / `DatasetStatusRecord` /
   `SiblingStatusRecord` are explicitly deferred — they are an optimization
   for typed call sites, and v1 has zero typed call sites.
6. **`extras` must NOT appear as a key in iteration / serialization.** It is
   spliced into iteration; from the outside the record looks flat.

### 3.2 MutableMapping implementation (sketch)

```python
def __post_init__(self):
    object.__setattr__(self, '_DECLARED',
                       frozenset(f.name for f in fields(self)
                                 if f.name not in ('extras',)))

def __getitem__(self, key):
    if key in self._DECLARED:
        v = getattr(self, key)
        if v is None:
            raise KeyError(key)
        return v
    return self.extras[key]

def __setitem__(self, key, value):
    if key in self._DECLARED:
        setattr(self, key, value)
    else:
        self.extras[key] = value

def __delitem__(self, key):
    if key in self._DECLARED:
        if getattr(self, key) is None:
            raise KeyError(key)
        setattr(self, key, None)
    else:
        del self.extras[key]

def __iter__(self):
    for name in self._DECLARED:
        if getattr(self, name) is not None:
            yield name
    yield from self.extras

def __len__(self):
    return sum(1 for _ in self)

def __contains__(self, key):
    if key in self._DECLARED:
        return getattr(self, key) is not None
    return key in self.extras

def __eq__(self, other):
    if isinstance(other, (StatusRecord, dict)):
        return dict(self) == dict(other)
    return NotImplemented
```

`@dataclass(eq=False)` is used so the dataclass's default `__eq__` (which would
compare across declared fields only and not consider Mapping equivalence) does
not collide with the explicit Mapping-style `__eq__` above.

### 3.3 Construction ergonomics

`get_status_dict` accepts `**kwargs` for arbitrary keys. The class needs the
same. Strategy: `get_status_dict` partitions kwargs into declared-fields and
extras and passes them to the constructor:

```python
def get_status_dict(action=None, ds=None, ..., **kwargs):
    # ...existing body, but build a StatusRecord at the end:
    declared = StatusRecord._declared_field_names()  # cached
    declared_kw = {k: v for k, v in d.items() if k in declared}
    extras = {k: v for k, v in d.items() if k not in declared}
    return StatusRecord(**declared_kw, extras=extras)
```

This is the only line of "real" logic the migration adds outside the class.

The manual `dict(res_kwargs, status='ok', ...)` spread sites are **not** rewritten
in v1. They keep producing plain dicts. Consumers handle both.

### 3.4 JSON serialization

`_render_result_json` (`interface/utils.py:432`) currently does
`json.dumps({k: v for k, v in res.items() if k != 'logger'}, default=str)`. With
`MutableMapping` this keeps working unmodified, *provided* the iteration order
and key set match the current dict shape. **This is the single most important
backward-compat invariant** — it is what users programmatically consume. Add a
golden-record test that captures the current JSON output for a representative
result and asserts the dataclass produces identical bytes.

### 3.5 Pickling

`MutableMapping` + `@dataclass` is picklable by default. The only weird field
is `logger`, which is already popped before the record crosses the parallel
boundary in `_process_results`. Add an explicit `pickle.dumps`/`pickle.loads`
round-trip test.

## 4. Phased rollout

### Phase 1 — single PR, minimal diff (this branch)

**Files touched:**

- `datalad/interface/results.py` — add `StatusRecord` class, route
  `get_status_dict`'s final `return d` through `StatusRecord(...)`. ~150 lines
  added, ~5 lines changed.
- `datalad/interface/tests/test_results.py` (or a new
  `test_status_record.py`) — add the test suite below. New file.
- `docs/designs/status-record.md` — this document.

**Tests:**

- Dict semantics: `r['x']`, `r.get('x')`, `'x' in r`, `r.pop('x')`,
  `r['x'] = 1`, `dict(r)`, `r.items()`, `r.keys()`, `r.values()`, `len(r)`,
  iteration order matches `get_status_dict` plain-dict baseline.
- Equality: `StatusRecord(...)` == `get_status_dict_old(...)` for a battery
  of representative inputs.
- JSON serialization: `json.dumps(StatusRecord(...))` is byte-identical to
  `json.dumps(dict_baseline)` for the same inputs (sorted keys).
- Spread: `dict(other, **r)` and `dict(r, **other)` produce the same dicts
  as before.
- Constraint: `EnsureKeyChoice('action', ('install',))(StatusRecord(action='install'))`
  succeeds.
- Hooks: `match_jsonhook2result(hook, StatusRecord(...), match)` returns the
  same boolean as against the equivalent dict.
- Pickling: `pickle.loads(pickle.dumps(r))` round-trips and equals `r`.
- `extras` is not visible: `'extras' not in r`, `'extras' not in r.keys()`,
  `'extras' not in json.loads(json.dumps(dict(r)))`.
- Mutation: arbitrary `r['some_new_key'] = 1` lands in `extras` and shows up
  in iteration.

**Acceptance:**

- Full test suite passes.
- `datalad ... -f json` output is byte-identical for representative commands
  (`status`, `save`, `clone`, `get`, `siblings`, `push`) against a recorded
  baseline.
- Diff is small enough to review in one pass: roughly one new class + tests +
  this doc, no edits to other files.

### Phase 2 — design validation via end-to-end migration (staged immediately after v1)

v1 alone proves the class works as a dict. **v2 is where the design is actually
exercised** — only by converting producers and consumers across the codebase do
we learn:

- Whether the chosen typed fields are the right ones.
- Whether the action-specific clusters (file / dataset / sibling / annex-json)
  are *real* — i.e. consistent enough to deserve subclasses, or mushy enough
  that a single flat class with `extras` is the right answer.
- Whether `extras` is comfortable as the escape hatch, or routinely painful.
- Which consumer patterns survive attribute-access conversion and which do
  not (e.g. dynamic key names, dict-spread, `.pop`).
- Whether validation can be turned on without breaking any in-tree producer.

v2 is therefore framed as a **probe**, not a checklist. Each sub-PR's job is
both to convert code *and* to surface concrete feedback that may force changes
to the v1 class shape (extra fields, removed fields, renamed `extras`, slot
optimization, subclass set, etc.). The plan deliberately does *not* commit to
the final subclass set up front — that is decided by the data v2 produces.

v2 is split into reviewable sub-PRs, each independently revertable:

#### v2.1 — convert manual-dict construction sites

Targets:

- `datalad/core/local/status.py:188-194,420-424`
- `datalad/core/distributed/push.py:216-224`
- `datalad/distribution/siblings.py:599-603,770-773`
- `datalad/core/local/save.py:374-380`
- `datalad/local/addurls.py:930-951`

For each: replace `dict(res_kwargs, status='ok', ...)` with
`StatusRecord(**res_kwargs, status='ok', ...)`. Audit `res_kwargs` at each
call: which keys flow in? Are any of them ones that should be promoted from
`extras` to typed fields? Record findings in this doc as a table.

Exit criterion: all five sites converted; JSON byte-identity tests still
green; **list of any `extras` keys that appear in ≥2 of the five sites
recorded as candidates for promotion to typed fields in v2.3**.

#### v2.2 — convert dict-style read access in central consumers

Targets (the consumers that read every result, not the producers):

- `datalad/interface/utils.py` — `_process_results`, `generic_result_renderer`,
  `_render_result_generic`, `_render_result_json`, `keep_result`.
- `datalad/interface/base.py` — `eval_results` decorator's result loop.
- `datalad/interface/results.py` — `ResultXFM` subclasses (`YieldDatasets`,
  `YieldRelativePaths`, `YieldField`), `is_ok_dataset`, `count_results`,
  `only_matching_paths`, `is_result_matching_pathsource_argument`.

For each: convert `res.get('status')` → `res.status`,
`res.get('path')` → `res.path`, etc., where the key is a typed field. Leave
`res.get(dynamic_key)` and `res[<extras-key>]` as dict access. The aim is
*partial* attribute adoption — wherever the type checker can help.

`_render_result_json` keeps its `dict(res)` snapshot; it must produce identical
JSON. `match_jsonhook2result` keeps full dict semantics — user matches name
arbitrary keys.

Exit criterion: full test suite + JSON byte-identity tests green; mypy/pyright
run on the touched files reports zero net new errors; **list of read-paths
that fell back to dict access (dynamic key, `extras`, `.pop`) recorded as
input to v2.4**.

#### v2.3 — promote-or-park decision; introduce subclasses *iff justified*

Inputs from v2.1 + v2.2. Decision rules:

- A field graduates from `extras` to a typed attribute on `StatusRecord` iff
  it appears in ≥3 producer sites or ≥1 consumer site outside its origin
  command.
- A subclass (`FileStatusRecord`, `DatasetStatusRecord`,
  `SiblingStatusRecord`, `AnnexJsonRecord`) is introduced iff ≥3 fields
  cluster consistently across ≥2 callers *and* a typed call site can use
  the subclass to eliminate at least one `cast` / `assert`.
- Otherwise the field stays in `extras` and the subclass is not created.

Candidate clusters from the audit (subject to v2.1/v2.2 confirmation):

| Candidate subclass | Action(s) | Fields under consideration |
|---|---|---|
| `FileStatusRecord` | `status`, `diff`, `save`, `get`, `add` | `state`, `gitshasum`, `prev_gitshasum`, `bytesize`, `key`, `annexkey` |
| `DatasetStatusRecord` | most dataset-level results | `gitshasum`, `prev_gitshasum`, `branch` |
| `SiblingStatusRecord` | `siblings`, `create-sibling-*` | `name`, `url`, `ssh_url`, `annex-ignore` (note: hyphen → stays in `extras`) |
| `AnnexJsonRecord` | results from `annexjson2result` | `annexkey`, `metadata` |

Each subclass that survives the decision rule is added in its own sub-PR with
a single producer migrated to it (e.g. `core/local/status.py` for
`FileStatusRecord`). If a candidate fails the rule, this doc is updated with
the reason ("`branch` only used by 1 producer; staying in `extras`") and the
class is *not* created.

Exit criterion: subclass set frozen and documented in `docs/source/design/result_records.rst`.

#### v2.4 — opt-in strictness and validation

Once v2.1–v2.3 have shaken out the field set, add:

- Status-value validation: `__setitem__('status', v)` raises if `v` not in
  `{'ok', 'notneeded', 'impossible', 'error'}`. Only added if v2.1/v2.2
  produced no offenders; otherwise this is documented as a future step.
- Optional warning on `__setitem__` of an unknown key, gated by
  `DATALAD_STATUSRECORD_STRICT=1`, off by default. The warning's value is in
  CI / development; production stays silent.
- Optional `slots=True` if microbenchmarks show measurable overhead
  (Python 3.10+). Only if numbers warrant it.

Exit criterion: validation either lands cleanly (no producer changes needed)
or this doc records the offending sites and defers to a v3 cleanup pass.

#### v2.5 — annotate hot-path return types

Now that consumers read typed attributes, annotate the return types of
`get_status_dict`, `annexjson2result`, `results_from_paths`,
`results_from_annex_noinfo`, and the `eval_results` decorator's yielded type.
This is pure annotation — no behavior change. Smallest possible diff.

Exit criterion: annotations land; mypy/pyright run is clean for
`datalad/interface/`.

### Phase 3 — opportunistic, no fixed timeline

These are opt-in cleanups that do not affect the design and can land
piecemeal as the codebase is touched for other reasons. Listed here so they
do not get re-discovered as "what's next" after v2:

- Annotate yielded types on individual command implementations
  (`Iterator[StatusRecord]`).
- Migrate remaining `res.get('k')` → `res.k` in non-central consumers.
- Convert third-party / extension-facing helpers (`is_ok_dataset` etc.) to
  accept either `StatusRecord` or a plain dict (already true; just document).
- Pydantic / msgspec model for the external `-f json` schema, with a `$schema`
  URL. This is a *new* API surface, not a migration step.

### Exit criteria for the migration as a whole

The migration is "done" when:

1. `get_status_dict` returns a `StatusRecord`.
2. All in-tree producers either go through `get_status_dict` or directly
   construct a `StatusRecord` / subclass.
3. Central consumers (`eval_results`, renderers, `ResultXFM`) read typed
   attributes for the standard fields.
4. The subclass set is frozen and documented.
5. `docs/source/design/result_records.rst` is updated to describe the typed
   class; the dict shape becomes a *protocol* the class implements, not the
   primary representation.
6. `-f json` output remains byte-identical to the pre-migration baseline.

Until #6 is at risk, the migration is reversible.

## 5. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **User hooks break** because key set or iteration changes | Golden-record JSON tests; keep all current keys; do not rename |
| **Performance regression** in tight result loops | Microbenchmark `get_status_dict` before/after; if needed, `@dataclass(slots=True)` (Python 3.10+) |
| **Pickle breakage** across multiprocessing boundaries | Explicit pickle round-trip test |
| **`extras` accidentally surfaces in iteration / JSON** | Test asserts `'extras'` is never in `keys()`, `items()`, JSON output |
| **`__eq__` collides between dataclass and Mapping** | `@dataclass(eq=False)` and explicit Mapping-style `__eq__` |
| **`logger.pop` semantics change** | Test `r.pop('logger', None)` returns the logger and afterwards `'logger' not in r` |
| **`annex-ignore` (hyphenated) is invalid as identifier** | Stays in `extras` — that is exactly its purpose |
| **Diff bloat from incidental annotation churn** | Hard rule: v1 PR touches `interface/results.py` + tests + this doc only |

## 6. Open questions for discussion

These do not block v1 — flagging for the follow-up phases.

1. **Should `get_status_dict` be renamed?** It now returns a `StatusRecord`,
   not a dict. Renaming aids discoverability but is wider churn. Suggest:
   keep it (it's the public extension API), add `StatusRecord(...)` as the
   typed entry point for new code.
2. **`exception` typing**: today the field can hold either a raw `Exception`
   or a `CapturedException`. Keep the union, or coerce to `CapturedException`
   in `__post_init__`? Coercing is cleaner but changes observable behavior
   for user hooks. Suggest: keep the union.
3. **Strictness of `extras`**: should `__setitem__` of an unknown key warn?
   Suggest: not in v1; later, opt-in via env var.
4. **Subclass `action` as `Literal`?** Pro: types catch bugs. Con: every new
   action becomes a code change. Suggest: leave as `str`.
5. **Module placement**: `datalad/interface/results.py` is the obvious home
   for v1 (where `get_status_dict` lives). Splitting into
   `datalad/interface/status_record.py` is cosmetic; defer.
