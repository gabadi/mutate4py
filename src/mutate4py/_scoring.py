"""One finished scored run's verdicts, in the shape the Manifest records."""

import dataclasses

from mutate4py._discovery import Site


@dataclasses.dataclass(frozen=True)
class ScoredRun:
    """A run's Sites, coverage, selection and survivors, as the Manifest score block needs them.

    full_selection is True only for a full-file run (no differential narrowing).
    Apart from a changed function (hash changed, tests digest changed or Unscored), only such a run may
    score a function with no covered Site: a narrowed run never tested it, so the function's recorded
    score must stay as it was.

    recorded_survivors holds the (function id, line, desc) survivors the Manifest recorded before this run.
    changed_fn_ids holds the functions the run re-scores (ADR 0029 rule 1): a run scores one even when no
    covered Site reaches it. A changed function's stored score is stale, and an Unscored one has none, so
    leaving it unscored would cost a second run before the skip returns.
    """

    all_sites: list[Site]
    covered_lines: set[int]
    selected_sites: list[Site]
    survivors: list[Site]
    markers: dict[int, str] = dataclasses.field(default_factory=dict)
    full_selection: bool = False
    recorded_survivors: frozenset[tuple[str, int, str]] = frozenset()
    changed_fn_ids: frozenset[str] = frozenset()

    def unaccepted(self) -> list[Site]:
        """Survivors whose line carries no equivalent marker, in survivor order."""
        return [s for s in self.survivors if s.line not in self.markers]

    def accepted(self) -> list[tuple[Site, str]]:
        """Survivors whose line carries an equivalent marker, with its reason, in survivor order."""
        return [(s, self.markers[s.line]) for s in self.survivors if s.line in self.markers]

    def function_scores(self, function_ids: list[str]) -> dict[str, dict]:
        """Score block per named function id.

        A function is skipped when any of its covered Sites was not selected: it was only
        partly tested, so its old score is not replaced. A function with no covered Site is
        skipped too, unless the run is a full-file run. A narrowed run also skips a function whose recorded
        survivor has an uncovered Site. Module-level Sites (function_id "")
        are never looked up, because function_ids holds only named ids.
        """
        selected = set(self.selected_sites)
        scores = {}
        for fid in function_ids:
            block = self._score_block(fid, selected)
            if block is not None:
                scores[fid] = block
        return scores

    def _score_block(self, fid: str, selected: set[Site]) -> dict | None:
        """One function's score block, or None when the function is skipped."""
        sites = self._sites_of(fid)
        covered = self._covered(sites)
        if self._skipped(fid, covered, selected) or self._lost_recorded_survivor(fid):
            return None
        unaccepted = self._unaccepted_of(fid)
        accepted = self._accepted_of(fid)
        survived = len(unaccepted) + len(accepted)
        return {
            "score": {
                "killed": len(covered) - survived,
                "survived": survived,
                "uncovered": len(sites) - len(covered),
            },
            "survivors": [{"line": s.line, "desc": s.desc} for s in unaccepted],
            "accepted": [{"line": s.line, "desc": s.desc, "reason": r} for s, r in accepted],
        }

    def _skipped(self, fid: str, covered: list[Site], selected: set[Site]) -> bool:
        """Partly selected functions are skipped; so is one with no covered Site, unless the run is
        a full-file run or the function is changed (its hash moved, or it is Unscored)."""
        if not covered:
            return not (self.full_selection or fid in self.changed_fn_ids)
        return not all(s in selected for s in covered)

    def _lost_recorded_survivor(self, fid: str) -> bool:
        """A narrowed run skips a function whose recorded survivor has an uncovered Site.

        The Site matches the survivor on (line, desc). A full-file run retests every Site, so it never skips here.
        """
        if self.full_selection:
            return False
        return any(
            (fid, s.line, s.desc) in self.recorded_survivors and s.line not in self.covered_lines
            for s in self._sites_of(fid)
        )

    def _sites_of(self, fid: str) -> list[Site]:
        return [s for s in self.all_sites if s.function_id == fid]

    def _covered(self, sites: list[Site]) -> list[Site]:
        return [s for s in sites if s.line in self.covered_lines]

    def _unaccepted_of(self, fid: str) -> list[Site]:
        return sorted((s for s in self.unaccepted() if s.function_id == fid), key=lambda s: s.index)

    def _accepted_of(self, fid: str) -> list[tuple[Site, str]]:
        return sorted(((s, r) for s, r in self.accepted() if s.function_id == fid), key=lambda pair: pair[0].index)
