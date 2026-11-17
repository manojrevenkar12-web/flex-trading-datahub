# How this was built with a coding agent

The repository was written with Claude Code, with a person deciding what to build and checking the numbers.

- **The world came first.** Before any dbt model, the agent wrote the simulated portfolio and its raw feeds, with the
  faults each source really has: substitute values, a metering operator without UTC offsets, counter resets, trade
  amendments, the preliminary imbalance price. The settings were written down in `config/world.yaml` before the first
  result. A warehouse that is only tested on clean data proves very little.
- **A first version to beat.** `ftd/eval/naive.py` is the SQL a capable engineer writes on day one. Every model in
  `dbt/` had to earn its place by a measured difference against it on the same files.
- **Tests the agent could not argue with.** The invariant tests stop the warehouse from reading the truth; the dbt
  tests stop it from shipping a day with the wrong number of quarter hours or a feature from after the gate.
- **Numbers in the README come from the reports.** `python -m ftd.eval.cli readme --check` fails in CI when the
  README and `reports/` disagree, so no number was typed by hand.
- **The held-out month was written before it was run, and run once.** The gate was fixed after the first dev results.
  What the held-out month showed is in [heldout.md](heldout.md); fixes were measured on dev only.

Things the agent got wrong and the evaluation caught: positions rounded to zero at a 0.1 MW lot size for a portfolio
this small, a stuck register that changed value from day to day (so it was never found), and a feature join that
duplicated rows on the night summer time ends.
