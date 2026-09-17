# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## MANDATORY: Read before making any code changes

You MUST read `CONTRIBUTING.md` before making any code changes, commits, or pull requests.
It contains the authoritative project conventions including:
- Branch and commit naming prefixes (NF, BF, RF, DOC, CI, UX, TST, etc.)
- Code style rules (line length, imports, external_versions usage)
- Testing and linting commands
- PR labeling and changelog workflow
- Release branch workflow (master vs maint)

Do NOT guess or assume conventions — read the file. Additional documentation
may be found under `docs/`.

## Commit authorship

The git **author** of a commit you create is the person you are working for,
not the assistant — set `user.name`/`user.email` accordingly (e.g.
`git -c user.name=... -c user.email=... commit`) if the environment's git
identity says otherwise. Credit the model in the `Co-Authored-By:` trailer
instead. GitHub counts commit authors, not trailers, towards the repository's
contributor list; see `CONTRIBUTING.md`, section "Recognizing contributions".
