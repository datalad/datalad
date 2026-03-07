# Design: Flexible Recursion Filtering for Subdataset Operations

## Status: Draft

## Problem

DataLad's recursive operations (`get -r`, `install -r`, `foreach-dataset -r`,
`push -r`, etc.) currently offer only blunt control over which subdatasets are
included:

- **`-R N`** — integer depth limit; no semantic awareness.
- **`-R existing`** — only in `get`; skips absent subdatasets.
- **`datalad-recursiveinstall=skip`** — binary annotation in `.gitmodules`;
  checked only in `_recursive_install_subds_underneath()`, not in path-targeted
  installation, and not by other recursive commands.

None of these address real-world needs like:

- Skip `derivatives/NAME/sourcedata/raw` when its `.gitmodules` URL
  (`../../sourcedata/raw`) points to a dataset already present in the
  superdataset tree.
- Install only subdatasets pointing to a specific server.
- Filter by custom annotations/tags in `.gitmodules`.

## Design principle: consistency with `-R`

Throughout this design, `--r-filter` follows the same behavioral patterns as
`-R` (recursion limit):

- Filtered-out subdatasets are silently skipped (same as `-R` depth cutoff).
- Explicit paths override filters (same as `-R` and
  `datalad-recursiveinstall=skip` behavior — explicit path-targeted
  installation is not affected by filters).
- `--r-filter` composes naturally with `-R` and `-r`.

## Proposal

### 1. New generic parameter: `--recursion-filter EXPR`

Add to `common_opts.py` alongside `recursion_flag` and `recursion_limit`:

```python
recursion_filter = Parameter(
    args=("--r-filter",),
    metavar="EXPR",
    action='append',
    doc="""filter expression to select subdatasets during recursive
    operations. Multiple filters can be given; all must match for a
    subdataset to be included. See FILTER EXPRESSIONS below.""")
```

Naming convention: all recursion-related options use the `--r-` prefix to
harmonize with `-r`/`--recursive`. In the future, `-R` could also gain a
long form `--r-limit`.

This parameter is **independent of `-R`** — they compose naturally:

```bash
datalad get -r -R 3 --r-filter 'url!~^\.\.' .
```

All ~14 commands that delegate recursion through `ds.subdatasets()` →
`_get_submodules()` gain filtering support by threading this parameter through.

#### Per-command filtering considerations

Filtering operates on the subdataset record from `.gitmodules` — properties
like `url`, `name`, `datalad-id` are available **before** the subdataset is
installed. This means filtering works naturally for:

- **`get`/`install`** — filter decides which absent subdatasets to clone.
  All `.gitmodules` properties are readable from the parent even when the
  subdataset is absent. `.state` lets you filter on `present`/`absent`.
- **`foreach-dataset`** — typically operates on `state='present'` subdatasets;
  filtering adds property-based selection on top.
- **`clean`/`configuration`/`unlock`** — operate on present subdatasets;
  filtering works the same way.
- **`update`/`siblings`/`create-sibling-*`** — operate on present subdatasets;
  filtering can select which to update/configure.
- **`drop`** — uses `bottomup=True` and `state='present'`; filtering would
  control which present subdatasets to drop. E.g.,
  `--r-filter 'url~=archival-server'` to only drop data from a specific source.

### 2. Filter expression syntax

Keep it simple and shell-friendly. Each `--r-filter EXPR` is one predicate.
Multiple predicates are ANDed.

```
KEY=VALUE         exact string match
KEY!=VALUE        exact string non-match
KEY~=REGEX        Python regex search (re.search)
KEY!~REGEX        Python regex non-search
KEY?              property exists and is non-empty
KEY!?             property is absent or empty
```

Examples:

```bash
# Skip subdatasets with relative-parent URLs
--r-filter 'url!~^\.\.'

# Only subdatasets pointing to a specific org
--r-filter 'url~=github\.com/myorg'

# Only present subdatasets
--r-filter '.state=present'

# Only subdatasets with a specific custom tag
--r-filter 'datalad-install-group=core'

# Combine: absent subdatasets whose URL is not relative
--r-filter '.state=absent' --r-filter 'url!~^\.\.'
```

### 3. Filter keywords (property namespace)

At the filtering point in `_get_submodules()` (~line 335 of `subdatasets.py`),
each subdataset record `sm` contains:

**Internal properties** (dot-prefixed):

| Keyword        | Type   | Description                              |
|----------------|--------|------------------------------------------|
| `.state`       | str    | `'present'` or `'absent'`               |
| `.path`        | str    | absolute path to subdataset              |
| `.parentds`    | str    | absolute path to parent dataset          |
| `.gitshasum`   | str    | SHA1 of recorded commit in parent        |
| `.relative-url-in-tree` | str | computed: see Section 5 (`present`/`potential`/`false`) |

**`.gitmodules` properties** (bare keywords):

| Keyword        | Description                                    |
|----------------|------------------------------------------------|
| `url`          | URL from `.gitmodules`                         |
| `name`         | submodule name                                 |
| `datalad-url`  | DataLad-specific URL                           |
| `datalad-id`   | dataset UUID                                   |
| `datalad-recursiveinstall` | existing skip annotation              |
| `<anything>`   | any custom property set in `.gitmodules`        |

Note: `datalad-recursiveinstall` is a `.gitmodules` property and thus accessed
as a bare keyword (not dot-prefixed). The computed property
`.relative-url-in-tree` is internal and thus dot-prefixed.

#### Namespace rules

Two namespaces, no overlap, no fallback:

- **Bare keywords** (`url`, `name`, `datalad-id`, etc.) → `.gitmodules`
  properties. Internally looked up as `gitmodule_<keyword>` in the record.
- **Dot-prefixed keywords** (`.state`, `.path`, `.relative-url-in-tree`, etc.) →
  internal/computed properties.

```
Lookup for keyword K:
1. If K starts with '.':  strip dot, look up as internal/computed property
2. Otherwise:             look up as 'gitmodule_K' in record
3. Not found → "absent" for ?/!? operators, no match for =/!=/~=/!~
```

No `gitmodule_` prefix is needed or supported in filter expressions — bare
names map directly. No fallback between namespaces.

### 4. Implementation location: `_get_submodules()` in `subdatasets.py`

This is the central chokepoint for subdataset enumeration. All commands using
"Strategy A" (delegate to `ds.subdatasets()`) benefit immediately:

- `get`, `install`, `foreach-dataset`, `clean`, `update`, `siblings`, `drop`,
  `create-sibling-*`, `configuration`, `unlock`

Commands using the diff/status recursion path (`push`, `save`, `status`,
`diff`) would need separate work and are out of scope for the initial
implementation.

#### Insertion point

In `_get_submodules()`, after `state` is determined (~line 335) and before
`to_report` (~line 338):

```python
# existing
if not sm_path.exists() or not GitRepo.is_valid_repo(sm_path):
    sm['state'] = 'absent'
else:
    assert 'state' not in sm
    sm['state'] = 'present'

# >>> NEW: apply recursion filter
if parsed_filters and not match_filters(sm, parsed_filters):
    continue

# existing
to_report = paths is None \
    or any(p == sm_path or p in sm_path.parents
           for p in paths)
```

The filter is also passed through to the recursive call at ~line 433.

#### Interaction with `datalad-recursiveinstall=skip`

The existing hardcoded check in `get.py:482-486` becomes a **special case**
of the generic filter. For backward compatibility, `datalad-recursiveinstall=skip`
continues to work even without `--r-filter`. But users could equivalently write:

```bash
--r-filter 'datalad-recursiveinstall!=skip'
```

Both apply together: they AND. The hardcoded `datalad-recursiveinstall=skip`
check runs first (backward compatibility), then `--r-filter` provides
additional filtering on top. This means `--r-filter` cannot override the
hardcoded skip — it can only add more restrictions.

### 5. Computed property: `.relative-url-in-tree`

A simple regex on the URL (like `url!~^\.\.'`) is insufficient. Consider:

```
superdataset/
  sourcedata/raw/          (datalad-id: abc123)
  derivatives/sub1/
    sourcedata/raw/        (url: ../../sourcedata/raw, datalad-id: abc123)
```

Here `../../sourcedata/raw` resolves to `superdataset/sourcedata/raw`, which
IS in the tree and matches the `datalad-id` — safe to skip.

But if `sourcedata/raw` is not installed at the top level, or it exists but
has a different `datalad-id`, then we DO want to install the subdataset under
`derivatives/sub1/` to get the actual data.

A simple URL regex cannot distinguish these cases. We need a **computed
property** that performs runtime resolution.

#### Tri-state values

`.relative-url-in-tree` uses tri-state values to provide fine-grained control:

- **`present`** — the resolved target exists as an installed dataset, and if
  a `datalad-id` is declared, it matches.
- **`potential`** — the UUID matches via the parent's `.gitmodules` but the
  target dataset is not currently installed.
- **`false`** — no match: URL is not relative, resolves outside the tree,
  or IDs don't match.

Usage with `--r-filter`:

```bash
# Skip subdatasets whose target is already installed in the tree
datalad get -r --r-filter '.relative-url-in-tree=false'

# Skip both present and potential interlinks
datalad get -r --r-filter '.relative-url-in-tree!~present|potential'
```

#### Which URL: `url` vs `datalad-url`

Either `gitmodule_url` or `gitmodule_datalad-url` (or both) could be the
relative path:

- `gitmodule_url` — the git-native URL; typically the relative path for
  within-tree references (e.g. `../../sourcedata/raw`).
- `gitmodule_datalad-url` — records the original clone URL; could also be
  relative if the subdataset was added with `datalad clone ../../sourcedata/raw`,
  or could be a datalad-specific scheme like `ria+ssh://...`.

The computed property checks **both**. If either one is a relative path that
resolves to a matching dataset in the tree, the subdataset is interlinked.

#### Definition of `.relative-url-in-tree`

A subdataset's `.relative-url-in-tree` is determined by checking, for **any**
of `gitmodule_url` and `gitmodule_datalad-url`, ALL of the following:

1. The URL is a **relative path** (a `PathRI` that is not absolute).
2. Resolving that relative path against the subdataset's location within the
   **reference (top-level) dataset** yields a path that falls **within** the
   reference dataset tree.
3. If `gitmodule_datalad-id` is set, the installed dataset at the resolved
   path (or the parent's `.gitmodules` record for that path) has a
   **matching** `datalad-id`.

Then:
- If all conditions hold and the target path exists as an installed dataset:
  → `present`
- If conditions 1-2 hold and ID matches via `.gitmodules` but target is not
  installed: → `potential`
- Otherwise: → `false`

#### Computation

In `_get_submodules()`, when the filter references `.relative-url-in-tree`,
compute it lazily:

```python
def _compute_relative_url_in_tree(sm, refds_path):
    """Check if any URL (url or datalad-url) resolves to a matching
    dataset already present in the reference dataset tree.
    Returns 'present', 'potential', or 'false'."""
    sm_path = sm['path']
    declared_id = sm.get('gitmodule_datalad-id', '')

    # Check both url and datalad-url — either could be the relative path
    for url_key in ('gitmodule_url', 'gitmodule_datalad-url'):
        url = sm.get(url_key, '')
        if not url:
            continue

        ri = RI(url)
        if not isinstance(ri, PathRI) or isabs(ri.path):
            continue

        # Resolve relative URL against subdataset's location in the tree
        resolved = Path(os.path.normpath(sm_path.parent / url))

        # Must be within the reference dataset
        try:
            resolved.relative_to(refds_path)
        except ValueError:
            continue

        # Check if it exists as a dataset
        if resolved.exists() and GitRepo.is_valid_repo(resolved):
            # If datalad-id is declared, it must match
            if declared_id:
                try:
                    target_ds = Dataset(resolved)
                    actual_id = target_ds.id
                    if actual_id != declared_id:
                        continue
                except Exception:
                    continue
            return 'present'

        # Target not installed — check if UUID matches via .gitmodules
        if declared_id:
            # TODO: look up datalad-id in parent's .gitmodules for that path
            return 'potential'

    return 'false'
```

The key insight: this uses the **subdataset's parent path** (not the
superdataset's remote URL) to resolve the relative URL, which correctly
handles nested cases like `derivatives/sub1/sourcedata/raw` with
URL `../../sourcedata/raw`. Both `url` and `datalad-url` are checked
because either could be the relative path depending on how the subdataset
was originally added.

### 6. Configuration default

Allow setting a default filter via config so users don't have to specify
`--r-filter` every time:

```ini
# In ~/.config/datalad/datalad.cfg or dataset's .datalad/config
[datalad "recursion"]
    filter = .relative-url-in-tree=false
```

Multiple values would be ANDed, same as multiple `--r-filter` arguments.
Command-line filters ADD to (AND with) config-based filters.

### 7. Rollout plan

#### Phase 1: Core infrastructure

1. Add `parse_filter_spec()` and `match_filters()` to new
   `datalad/support/filter.py`.
2. Add `recursion_filter` to `common_opts.py`.
3. Thread through `Subdatasets.__call__()` → `_get_submodules()`.
4. Add to `Get` — thread through `_recursive_install_subds_underneath()` and
   `_install_targetpath()`, passing filter to `ds.subdatasets()` calls and
   to recursive invocations.
5. Tests for filter parsing, matching, and integration with `subdatasets`
   and `get`.

#### Phase 2: Computed properties

1. Implement `.relative-url-in-tree` computed property.
2. Register computed properties so they are lazily evaluated only when
   referenced in a filter expression.
3. Tests for the interlinked-detection logic.

#### Phase 3: Propagation to all recursive commands

1. Add `recursion_filter` parameter to all commands that use
   `recursion_flag`/`recursion_limit` and delegate to `ds.subdatasets()`:
   `get`, `install`, `foreach-dataset`, `clean`, `update`, `siblings`,
   `drop`, `create-sibling-*`, `configuration`, `unlock`.
2. Add `datalad.recursion.filter` config support.
3. Documentation and handbook examples.

#### Phase 4 (future): diff/status path

1. Extend filtering to the diff/status recursion path used by `push`,
   `save`, `status`, `diff`. This requires reading `.gitmodules` properties
   in `_diff_ds()` / `yield_dataset_status()`, which currently don't have
   them.

### 8. Resolved questions

1. **Should filtered-out subdatasets still be yielded as results?**
   Same behavior as `-R` — silently skipped.

2. **Should `--r-filter` affect path-targeted installation?**
   Yes, stay consistent with `-R` handling — explicit paths override filter.
   `_install_necessary_subdatasets()` ignores filters for explicit paths,
   same as it ignores `datalad-recursiveinstall=skip`.

3. **OR logic?**
   Deferred until there's a concrete use case. Users can use regex alternation
   within a single filter: `url~=(pattern1|pattern2)`.

4. **Naming: `url-interlinked` vs alternatives?**
   `.relative-url-in-tree` — conveys that it checks whether a relative URL
   resolves to a dataset already within the superdataset tree.
