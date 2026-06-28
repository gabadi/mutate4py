# Cleaner Role — Operational Knowledge

## Boundary File Irreducible Minimum
The 15-mutation-site threshold is a trigger, not a hard gate. When all extractable testable logic is in `*_helpers.py` and remaining sites are Context class methods, subprocess calls, and guard clauses, document as "irreducible boundary minimum" and proceed. Do not loop indefinitely trying to reach 15.

## Test Error Messages Must Match New Implementation
When writing a test for a refactored function, verify expected error message strings match the new implementation before committing. Do not copy message strings from old code — refactored functions may use different error strings.

## Manifest "NEW" Hashes After Coder Handoff
When manifest entries show "NEW" hashes and stale line numbers after a coder handoff, this is expected — the mutation tool refreshes them on first scan. Do not hand-edit manifest entries; skip to cleanup work.
