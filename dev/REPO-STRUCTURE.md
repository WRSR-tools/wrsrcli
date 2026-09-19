# wrsrcli — Repo structure

## Folder: `dev/`

All documents relevant to the development of `wrsrcli`.

## Subfolder: `decisions/`

Each decision made is committed to this subfolder. File name is: `D-NNN - YYYY-MM-DD HHMM.md`. File should record what the issue was, potential tradeoffs, and clearly record the decision. Format:

```
# D-NNN - {One-line description}

- **Decided:** YYYY-MM-DD HH:MM

## Issue
{Issue and question at hand}

## Decision
{Decision as recorded}

## Superseded

{If superseded, give decision reference which superseded this decision and date and time.}
```

## Subfolder: `bugs/`

Each bug found is logged with filename: `B-NNN - YYYY-MM-DD HHMM.md`. Format:

```
# B-NNN - {One-line description}

- **Bug found:** YYYY-MM-DD HH:MM
  - Current app version: {last version number when found}
- **Assessed severity:** {grade}
- **Current state:** Not fixed|Fixed|Superseded/not relevant
- **Bug fixed:** YYYY-MM-DD HH:MM
  - Fixed during version: {last released version}

  ## Summary of bug
  {Describe bug here}

  ### Consequences for users
  {Describe how this impacts users of the tool}

  ## Summary of fix
  {Describe fix here}
```

## File: `Progress.md`  

Progress indicator as Markdown table. Format:

```
|Date|Time|Note|
|---|---|---|
|YYYY-MM-DD|HH:MM|Phase X started.|
|YYYY-MM-DD|HH:MM|Phase X finished. Total development time this phase: HH:MM.|

Total development time across all phases: HH:MM.
```



## Folder: `docs/`
Documentation for users. Include:

- Install.md

- Use.md

- Import.md
