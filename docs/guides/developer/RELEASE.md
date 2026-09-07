# Cutting a release

Written after v7.0.0, whose preparation found the same version number declared
in five places with only two of them right. Everything here exists because
something went wrong once.

A release of this project is also a **Zenodo deposit**: publishing the GitHub
release mints a DOI, and a DOI is permanent. What is wrong at tag time stays
wrong, and correcting it costs a new version of the deposit.

## 1. The version lives in five places

They drift silently, because nothing checks them against each other.

| File | Field |
|---|---|
| `pyproject.toml` | `version` |
| `src/zebtrack/__init__.py` | `__version__` |
| `CITATION.cff` | `version`, `date-released` |
| `.zenodo.json` | `version`, `publication_date` |
| `README.md`, `README.pt-BR.md` | the version badge |

`docs/INDEX.md` carries one too. Check them together:

```bash
grep -n "6\.\|7\." pyproject.toml src/zebtrack/__init__.py CITATION.cff \
  .zenodo.json docs/INDEX.md | grep -i version
grep -o "version-[0-9.]*-blue" README.md README.pt-BR.md
```

**`.zenodo.json`'s `version` overrides the tag name in the DOI record.** A tag
named `v7.0.0` with `"version": "6.0.0"` in that file produces a record labelled
6.0.0. It is the single most consequential field in the whole process.

## 2. Say which version the manuscripts evaluated

The archived tag is not necessarily the version the science was done with. As of
v7.0.0 the manuscripts report results from **4.0.0** (tag `v4.0.0`), and the
`.zenodo.json` description says so explicitly, with a pointer for exact
reproduction. Do not let the description claim the archived tag *is* the
evaluated version unless it is.

## 3. Gates that do not run locally

`bandit` and `pip-audit` are installed ad-hoc by CI (`ci.yml`, the `lint` job)
and are **not** in `pyproject.toml`. `pytest`, `ruff`, `mypy` and `pre-commit`
can all be green while `main` goes red.

```bash
python -m pip install bandit pip-audit
python -m bandit -r src/zebtrack -ll     # -ll = medium and above, as CI runs it
```

Relatedly: ruff does not enable the `S*` rules here beyond `S110`, so a
legitimate `# noqa: S310` shows up as an unused-noqa (RUF100). Removing it does
not remove the risk — bandit still enforces the rule.

## 4. Stacked pull requests do not run CI

`ci.yml` triggers on `pull_request: branches: [main]`. A PR whose base is
another feature branch runs **only** commitlint — no tests, no mypy, no coverage
ratchet, no security gates. Retargeting the base does not trigger CI either: the
workflow does not listen for the `edited` event.

Before merging a stacked PR, retarget it to `main` and push (or close and
reopen) so a real run happens.

Two more things about stacks, both learned the hard way:

- **Do not delete the base branch when merging.** GitHub closes any PR whose
  base ref disappears. The child PR cannot then be reopened; it has to be
  recreated.
- Squash merges give the parent's commits new SHAs, so rebase each child with
  `git rebase --onto origin/main <old-parent-tip> <child>`. Use `origin/main`,
  never the local `main`, which goes stale after every merge.

## 5. Checklist

Before tagging:

- [ ] All five version declarations agree, and `date-released` /
      `publication_date` match the day you will actually tag.
- [ ] `CHANGELOG.md` has a dated section for the version, `[Unreleased]` empty.
- [ ] `docs/releases/RELEASE_NOTES_v<version>.md` written — it becomes the
      release body.
- [ ] `CITATION.cff` has every author's ORCID.
- [ ] `NOTICE` describes how the weights are actually distributed. When they
      ship as release assets, the CC BY 4.0 attribution of the training dataset
      travels with them.
- [ ] Repository cleaned: the deposit is a snapshot of the tree, and dead files
      become permanent in a citable archive.
- [ ] `pytest -q`, `pytest -m gui -n0`, `ruff check .`, `mypy .`,
      `pre-commit run --all-files`, and the CI-only gates from §3.
- [ ] Zenodo integration enabled — verify it, do not assume it (see below).
- [ ] No stale draft release that could be published by accident. With the
      webhook active, publishing the wrong draft mints a DOI for the wrong tree.

Verifying the Zenodo hook:

```bash
gh api repos/MarkSant/DRerio-LogAI/hooks --jq '.[] | {events, active}'
```

An empty list means publishing the release mints no DOI at all. The webhook URL
contains an access token: do not paste it anywhere public.

Tagging and publishing:

1. Tag the merge commit on `main` and push the tag.
2. Create the release **as a draft**, with the release notes as the body.
3. Attach the weight files named in `weights_manifest.json`. Verify:

   ```bash
   poetry run fetch-weights --check
   ```

4. Publish. **This is the step that mints the DOI**, and it is reserved to the
   maintainer.

After the DOI exists:

- [ ] Paste it into `CITATION.cff` (uncomment the `doi` identifier) and the
      README.
- [ ] If a companion data deposit exists, cross-link the two records through
      `related_identifiers`.

## 6. Weights

The weights are attached to the release of the version itself, and
`weights_manifest.json` pins that tag. There is deliberately **no separate
weights release**: with the Zenodo webhook active, any release mints a DOI, and
Zenodo archives the tag's **source tarball, not the assets** — a weights-only
release would produce a record containing code and no weights.

A later version does not need to re-upload 200 MB: leave the manifest pointing
at the tag where the weights live until the weights themselves change. When they
do, regenerate and re-upload together:

```bash
poetry run fetch-weights --generate-manifest --release-tag v<new-version>
```
