# AGENTS.md

This file provides guidance to AI coding assistants (Claude Code, Codex,
Copilot, Cursor, ...) when working with code in this repository.

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
identity says otherwise. Credit the harness and the model in the
`Co-Authored-By:` trailer instead, e.g.

    Co-Authored-By: Claude Code 2.1.319 / Claude Opus 5.5 <noreply@anthropic.com>

GitHub counts commit authors, not trailers, towards the repository's
contributor list; see `CONTRIBUTING.md`, section "Recognizing contributions".

## Changelog fragment

Every pull request MUST include a scriv changelog fragment named
`changelog.d/pr-<NUMBER>.md`, where `<NUMBER>` is the pull request's number.
Do not leave it to the `CHANGELOG-missing` label: only maintainers can add
labels, and the snippet it generates from the PR title is rarely a good entry.
Open the pull request first, then commit the fragment to its branch -- or
predict the number as one more than the repository's latest issue or pull
request number, and rename the fragment if the prediction turns out wrong.  Follow
`CONTRIBUTING.md`, sections "CHANGELOG entries and labelling pull requests"
and "Writing the entry": pick the section matching the PR's `semver-*` label,
write the entry last and for users, and keep it to about 40 words.  Use the
existing fragments under `changelog.d/` as examples of the format.
