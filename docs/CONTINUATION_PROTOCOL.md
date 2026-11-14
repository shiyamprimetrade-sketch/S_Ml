# Continuation protocol

On Continue, read STATUS.md, EXPERIMENT_LEDGER.md and open PR metadata first.
Inspect the current branch head and changed files; preserve completed work and
account checkpoints. Resume the next unfinished acceptance item in ROADMAP.md.

Run `python -m unittest discover -s tests -v` from the repository or after package
installation. Never count zero discovered tests as a pass. Preserve raw private
observations and numeric checkpoints outside Git. Do not add account exports to
the public repository to make another session convenient.

Record the prior commit in STATUS.md before each commit (a file cannot contain
its own final commit hash). The branch HEAD and PR are the authoritative latest
commit. Record tests, data source state, model version, evidence and known gaps.
Do not restart this foundation when independent authorization is unavailable.
