"""How a pytest argv reads: which token is a flag, which is the value a flag takes,
and which is a positional argument.

Two readers need the same grammar and sit in different layers: the tests
fingerprint (`_tests_fingerprint`), which decides what a run reads, and the
per-Mutant dispatch (`_test_dispatch`), which strips the run's positional paths
from an argv. Both must read an argv the same way, so the grammar lives here in
`primitives`, where both reach it for free (see tach.toml's header).
"""

from collections.abc import Sequence

__all__ = ["FLAG", "POSITIONAL", "VALUE", "VALUE_OPTIONS", "flag_tokens", "positional_tokens", "token_roles"]

FLAG = "flag"
VALUE = "value"
POSITIONAL = "positional"

# pytest options whose value is the next argv token. That token is an option
# value, never a positional, even when it spells one (`-k tests`).
VALUE_OPTIONS = frozenset(
    {
        "-k",
        "-m",
        "-p",
        "-o",
        "-c",
        "-W",
        "-r",
        "-n",
        "--rootdir",
        "--ignore",
        "--ignore-glob",
        "--deselect",
        "--tb",
        "--maxfail",
        "--basetemp",
        "--junitxml",
        "--import-mode",
        "--log-level",
        "--capture",
        "--durations",
        "--confcutdir",
        "--override-ini",
    }
)


def token_roles(tokens: Sequence[str]) -> list[str]:
    """The role of each token: FLAG, VALUE (the value a value option takes), or POSITIONAL.

    A value option takes the token after it, so `-k tests` makes `tests` a VALUE.
    Any other token starting with `-` is a FLAG; a flag that carries its own value
    (`--rootdir=x`, `-kexpr`) takes no further token.
    """
    roles: list[str] = []
    value_next = False
    for token in tokens:
        if value_next:
            roles.append(VALUE)
            value_next = False
        elif token in VALUE_OPTIONS:
            roles.append(FLAG)
            value_next = True
        elif token.startswith("-"):
            roles.append(FLAG)
        else:
            roles.append(POSITIONAL)
    return roles


def flag_tokens(tokens: Sequence[str]) -> list[str]:
    """The tokens pytest reads as flags, value options included, in argv order."""
    return [token for token, role in zip(tokens, token_roles(tokens)) if role == FLAG]


def positional_tokens(tokens: Sequence[str]) -> list[str]:
    """The tokens pytest reads as positional arguments, in argv order."""
    return [token for token, role in zip(tokens, token_roles(tokens)) if role == POSITIONAL]
