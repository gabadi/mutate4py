"""Apply and restore source mutations for the run loop."""

from mutate4py._discovery import Site, _build_line_index, _abs_offset


def apply_mutant(source: str, site: Site) -> str:
    """Return source with the site's mutation spliced in."""
    line_index = _build_line_index(source)
    start = _abs_offset(line_index, site.line, site.col)
    end = _abs_offset(line_index, site.end_line, site.end_col)
    return source[:start] + site.mutant_text + source[end:]
