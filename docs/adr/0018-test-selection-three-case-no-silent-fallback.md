# A pytest run that runs no test aborts; a Survivor is confirmed with the full test set

A narrowed Mutant runs only the tests that reached its line. A Mutant run that ends in pytest exit 4 or 5 ran no test, and a Control run on the original code tells if the Mutant or the pytest argv caused it.

## Considered Options

- **A warning line instead of the abort.** Agents read the exit code and the Mutation Report only. With a warning, a Mutant that no test ran is scored `killed` and the run exits 0.
- **Remove exit 4 from the abort.** An argv that names a path that does not exist is a real defect, and pytest reports it with exit 4. Without the abort, each Mutant is scored `killed` while no test ran.
- **Find the cause of exit 4 in the pytest output** (match `ImportError while loading conftest`). It ties the rule to the pytest wording and to one failure shape. The Control run asks if this argv runs tests on the original code, and gives the same answer for each cause.
- **Widen the narrowed list instead of confirming Survivors.** A covering list comes from the lines that each test reaches, so it cannot name a test that matters only through state that it reads. Widening the list runs the full test set for each Mutant, which is the cost that narrowing exists to remove.
- **Confirm the Survivors of a swap or harness file on the fork server.** A forked child shares the imports of the primed parent, and that file is in the parent. A memoised body read from the parent is the state that confirmation must rule out.
