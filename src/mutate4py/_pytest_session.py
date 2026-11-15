"""What a pytest run reads, located the way pytest locates it: collection roots, where the inifile
search starts, and the directories whose conftest it loads.

`_tests_fingerprint` hashes these inputs, and `_plugin_neutralisation` reads the conftests among them to
see which plugins a run names. Both sit in `domain`, which may not import a sibling without a declared
dependency, so the shared reading lives here in `primitives` (see tach.toml). Stdlib and `primitives` only.
"""

import os
import re

from mutate4py._pytest_argv import VALUE_OPTIONS, flag_tokens, positional_tokens
from mutate4py._pytest_config import configured_testpaths
from mutate4py._pytest_inifile import ancestors
from mutate4py._py_tree import walkable_dirs

__all__ = ["collection_roots", "conftest_chain", "pytest_start", "run_conftests"]

# A flag that carries everything it needs: a bare switch, a value attached with `=`, or a value attached directly.
# A flag outside this set and outside VALUE_OPTIONS may consume the next token, so the walk widens instead.
_SELF_CONTAINED_FLAG = re.compile(r"-[vqsxl]+|--(lf|ff|pdb|trace|strict-markers|no-header)|--[\w-]+=.+|-[a-zA-Z].+")


def positional_roots(cwd: str, tokens: list[str]) -> list[str]:
    """Pytest's positional arguments, resolved against `cwd`; nodeid suffixes (`::name`) are dropped."""
    return [os.path.join(cwd, token.split("::")[0]) for token in positional_tokens(tokens)]


def _is_classified_flag(token: str) -> bool:
    """Whether this reader knows the flag's arity: a value option, or a flag that carries its own value."""
    return token in VALUE_OPTIONS or _SELF_CONTAINED_FLAG.fullmatch(token) is not None


def collection_roots(cwd: str, tokens: list[str]) -> list[str]:
    """Positional arguments, else configured testpaths, else the rootdir (here `cwd`).

    A flag this reader cannot classify may take the next token as its value, so the
    positional reading would be wrong. The walk then widens to the whole rootdir.
    """
    if not all(_is_classified_flag(token) for token in flag_tokens(tokens)):
        return [cwd]
    return positional_roots(cwd, tokens) or configured_testpaths(cwd) or [cwd]


def pytest_start(cwd: str, tokens: list[str]) -> str:
    """Where pytest starts its inifile search: the common ancestor of the existing positional paths, else `cwd`.

    `determine_setup` (findpaths.py:313) takes `get_common_ancestor` of the argument directories (:205-228,
    :231-250), which is the invocation directory when no argument names an existing path.
    """
    paths = [path for path in positional_roots(cwd, tokens) if os.path.exists(path)]
    directories = [path if os.path.isdir(path) else os.path.dirname(path) for path in paths]
    return os.path.commonpath(directories) if directories else cwd


def conftest_chain(root: str, bounds: list[str] | None) -> list[str]:
    """The directories above `root`, nearest first, whose conftest pytest loads.

    pytest skips a directory only when it is strictly above `confcutdir` (`_is_in_confcutdir`,
    config/__init__.py:682, :703-704). A bound at or below `root` therefore leaves no ancestor. A bound
    beside the chain skips only the ancestors it shares with the chain that are strictly above it. With
    several bounds, a directory is kept when any keeps it.
    """
    directories = ancestors(os.path.dirname(os.path.abspath(root)))
    if not bounds:
        return directories
    strictly_above = [set(ancestors(bound)[1:]) for bound in bounds]
    return [directory for directory in directories if any(directory not in above for above in strictly_above)]


def run_conftests(cwd: str, tokens: list[str], bounds: list[str] | None) -> list[str]:
    """Every conftest.py the run may load: those above each collection root up to `bounds`, and those beneath it.

    More than pytest loads, never fewer: a directory below a root is read whether or not collection reaches it.
    """
    found: list[str] = []
    for root in collection_roots(cwd, tokens):
        found.extend(os.path.join(d, "conftest.py") for d in conftest_chain(root, bounds))
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = walkable_dirs(dirs)
            found.extend(os.path.join(dirpath, name) for name in files if name == "conftest.py")
    return list(dict.fromkeys(path for path in found if os.path.isfile(path)))
