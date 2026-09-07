# FAPESP historical archive (legacy)

This folder records what was curated out of the public archive during the
FAPESP-funded development period, and why. Nothing of it remains as files: the
point of the note is the provenance, so that a reader of the Zenodo snapshot can
tell the difference between "this never existed" and "this was deliberately
removed".

## Removed before the v6.0.0 archival snapshot

Unpublished manuscript drafts (`manuscripts/`), FAPESP partial-report drafts
(`reports/`), grant proposal drafts (`proposals/`), and a financial spending
spreadsheet (`finance/`) were removed from the repository HEAD ahead of the
Zenodo-archived release: their contents are not appropriate for a permanent
public archive.

## Removed before the v7.0.0 archival snapshot

`git/` held twelve text files — the output of `git log`, `git tag` and commit
counts, committed as evidence of development history. They were removed for the
first public release: they are the repository's own history transcribed into the
repository, ~614 KB that any clone regenerates with a single command, and a
permanent citable archive is the wrong place to freeze a snapshot of it.

## Where the removed material still is

All of it remains reachable in the git history predating each removal commit,
for anyone who clones the full repository. It is excluded from the release
tarballs and therefore from the DOI snapshots.
