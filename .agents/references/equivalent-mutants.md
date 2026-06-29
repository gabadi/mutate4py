# Equivalent Mutant Categories — mutate4py Project

Recognized equivalent mutant patterns for this project. Surviving mutants in these categories do NOT need new tests — they are structurally equivalent for all valid inputs.

## Categories (from hardender session da863ce7, 2026-06-26)

1. **Falsy None vs False init** — replacing `None` with `False` (or vice versa) in initialization where the code only tests truthiness; both evaluate identically.

2. **argparse `dest=None`** — `dest` in argparse derives from the flag name; `dest=None` vs `dest="<flag>"` produces the same attribute name at runtime.

3. **Help-text mutations** — mutations inside `help="..."` strings for argparse arguments; help text has no behavioral effect.

4. **Single-comma DA lines with different `maxsplit`** — `_parse_da_line` mutations on lines that have exactly one comma; split with `maxsplit=1` or without produces the same result.

5. **Compare between-text with single operator occurrence** — `_mutate_compare` mutations where the between-text region contains exactly one operator; replace-first and replace-all are equivalent.

## Additional Categories (from hardender session 3b4f8734, 2026-06-28)

6. **`_cmd.run_command` `capture_output` variants** — mutants 5, 10, 13 in `_cmd.py`; `capture_output=True/False` variants produce identical behavior for the project's test inputs.

7. **`_copy_tree` `follow_symlinks=None/True`** — mutants 13, 14; the only distinction is for symlinks-to-directories, which crash with `IsADirectoryError` on both variants in the current call sites.
