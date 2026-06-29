import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from acceptance.steps.run_loop_steps import run_step

# Scenario data baked in; APS_FEATURE_JSON overrides for gherkin mutation
_aps_override = os.environ.get('APS_FEATURE_JSON')
if _aps_override:
    with open(_aps_override) as _f:
        _ir = json.load(_f)
    _background = _ir.get('background', [])
    _scenarios = _ir.get('scenarios', [])
else:
    _background = [{'keyword': 'Given', 'text': 'a Python source file with covered mutation sites'}, {'keyword': 'And', 'text': 'a baseline test command that passes'}]
    _scenarios = [{'name': 'the mutated test run outcome decides the status', 'steps': [{'keyword': 'Given', 'text': 'the mutated test run will "<outcome>"', 'parameters': ['outcome']}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'the progress line for that mutant shows status "<status>"', 'parameters': ['status']}, {'keyword': 'And', 'text': 'the report counts that mutant as "<tally>"', 'parameters': ['tally']}], 'examples': [{'outcome': 'exit nonzero', 'status': 'killed', 'tally': 'Killed'}, {'outcome': 'exceed timeout', 'status': 'timeout', 'tally': 'Killed'}, {'outcome': 'exit zero', 'status': 'survived', 'tally': 'Survived'}]}, {'name': 'the report tallies killed, survived, and uncovered', 'steps': [{'keyword': 'Given', 'text': '<killed> mutants exit nonzero and <timed> time out and <survived> exit zero', 'parameters': ['killed', 'timed', 'survived']}, {'keyword': 'And', 'text': 'there are <uncovered> uncovered sites', 'parameters': ['uncovered']}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'the output line "Killed: <killedTotal>" is printed', 'parameters': ['killedTotal']}, {'keyword': 'And', 'text': 'the output line "Survived: <survived>" is printed', 'parameters': ['survived']}, {'keyword': 'And', 'text': 'the output line "Uncovered: <uncovered>" is printed', 'parameters': ['uncovered']}, {'keyword': 'And', 'text': 'a "Survivors:" block is printed only when "<hasSurvivors>" is "yes"', 'parameters': ['hasSurvivors']}], 'examples': [{'killed': '2', 'timed': '1', 'survived': '0', 'uncovered': '0', 'killedTotal': '3', 'hasSurvivors': 'no'}, {'killed': '1', 'timed': '0', 'survived': '2', 'uncovered': '1', 'killedTotal': '1', 'hasSurvivors': 'yes'}, {'killed': '0', 'timed': '2', 'survived': '0', 'uncovered': '0', 'killedTotal': '2', 'hasSurvivors': 'no'}]}, {'name': 'the per-mutant progress line is the verbatim upstream format', 'steps': [{'keyword': 'Given', 'text': 'a single selected site on line 7 in function "func/calc" mutating "a > b" to "a >= b"'}, {'keyword': 'And', 'text': 'that mutant exits nonzero'}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'the output line "[1/1] killed line 7 a > b -> a >= b: func/calc" is printed'}], 'examples': []}, {'name': 'the mutant timeout is derived from the baseline duration', 'steps': [{'keyword': 'Given', 'text': 'the baseline takes "<baseline>" to pass', 'parameters': ['baseline']}, {'keyword': 'And', 'text': 'the timeout factor is "<factor>"', 'parameters': ['factor']}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'the mutant timeout is "<timeout>"', 'parameters': ['timeout']}], 'examples': [{'baseline': '2s', 'factor': '10', 'timeout': '20s'}, {'baseline': '10ms', 'factor': '10', 'timeout': '1s'}]}, {'name': 'a failing baseline aborts with no mutant applied and no backup', 'steps': [{'keyword': 'Given', 'text': 'the baseline test command fails'}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'the command exits with a non-zero status'}, {'keyword': 'And', 'text': 'the output contains "baseline failed:"'}, {'keyword': 'And', 'text': 'no mutant was applied'}, {'keyword': 'And', 'text': 'no ".mutate4py.bak" file is left behind'}, {'keyword': 'And', 'text': 'no "Mutation Report" is printed'}], 'examples': []}, {'name': 'effectiveSinceLastRun decides which covered sites are selected', 'steps': [{'keyword': 'Given', 'text': 'the file "<hasManifest>" an existing manifest', 'parameters': ['hasManifest']}, {'keyword': 'And', 'text': 'the flags supplied are "<flags>"', 'parameters': ['flags']}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'the run "<isDifferential>" differential', 'parameters': ['isDifferential']}, {'keyword': 'And', 'text': 'only "<selected>" sites are selected', 'parameters': ['selected']}], 'examples': [{'hasManifest': 'has', 'flags': '', 'isDifferential': 'is', 'selected': 'changed-function'}, {'hasManifest': 'has', 'flags': '--mutate-all', 'isDifferential': 'is not', 'selected': 'all-covered'}, {'hasManifest': 'has not', 'flags': '', 'isDifferential': 'is not', 'selected': 'all-covered'}, {'hasManifest': 'has', 'flags': '--since-last-run', 'isDifferential': 'is', 'selected': 'changed-function'}]}, {'name': 'the uncovered block visibility follows the differential switch', 'steps': [{'keyword': 'Given', 'text': 'the file "<hasManifest>" an existing manifest', 'parameters': ['hasManifest']}, {'keyword': 'And', 'text': 'the flags supplied are "<flags>"', 'parameters': ['flags']}, {'keyword': 'And', 'text': 'there is at least one uncovered site'}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'an "Uncovered mutations:" block "<visibility>" printed', 'parameters': ['visibility']}], 'examples': [{'hasManifest': 'has not', 'flags': '', 'visibility': 'is'}, {'hasManifest': 'has', 'flags': '', 'visibility': 'is not'}, {'hasManifest': 'has', 'flags': '--mutate-all', 'visibility': 'is'}, {'hasManifest': 'has not', 'flags': '--lines 7', 'visibility': 'is not'}]}, {'name': 'the run header prints the count lines and never a workers line', 'steps': [{'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'the output line "Mutation run:" is printed'}, {'keyword': 'And', 'text': 'the output lines "Total mutation sites:", "Covered mutation sites:", "Uncovered mutation sites:", "Changed mutation sites:", "Manifest exists:", "Selected mutation sites:" are printed'}, {'keyword': 'And', 'text': 'no "Mutation workers:" line is printed'}, {'keyword': 'And', 'text': 'no "worker-" token appears in any progress line'}], 'examples': []}, {'name': 'the over-threshold warning is conditional', 'steps': [{'keyword': 'Given', 'text': 'the file has "<total>" total mutation sites', 'parameters': ['total']}, {'keyword': 'And', 'text': 'the mutation warning threshold is "<threshold>"', 'parameters': ['threshold']}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'a "Warning: <total> mutation sites exceeds threshold <threshold>." line "<visibility>" printed', 'parameters': ['total', 'threshold', 'visibility']}], 'examples': [{'total': '51', 'threshold': '50', 'visibility': 'is'}, {'total': '50', 'threshold': '50', 'visibility': 'is not'}]}, {'name': 'the run restores the source and re-embeds the manifest', 'steps': [{'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'after the run the source has no mutant spliced in'}, {'keyword': 'And', 'text': 'the source ends with a fresh "mutate4py-manifest" footer'}, {'keyword': 'And', 'text': 'no ".mutate4py.bak" file is left behind'}], 'examples': []}, {'name': 'a pre-existing backup is restored at the start of the next run', 'steps': [{'keyword': 'Given', 'text': 'a ".mutate4py.bak" file exists from a previous interrupted run'}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'the output line "Restored source from backup (previous run was interrupted)." is printed'}, {'keyword': 'And', 'text': 'the source matches the backup before discovery proceeds'}], 'examples': []}, {'name': 'reusing coverage warns that the classification may be stale', 'steps': [{'keyword': 'Given', 'text': 'a readable LCOV file at the default coverage path'}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file with "--reuse-coverage"'}, {'keyword': 'Then', 'text': 'the output line "Reusing existing coverage; covered/uncovered classification may be stale." is printed'}, {'keyword': 'And', 'text': 'that line appears before the "Mutation run:" line'}], 'examples': []}]

def test_the_mutated_test_run_outcome_decides_the_status_0():
    """Scenario: the mutated test run outcome decides the status — example 0"""
    _s = _scenarios[0]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_mutated_test_run_outcome_decides_the_status_1():
    """Scenario: the mutated test run outcome decides the status — example 1"""
    _s = _scenarios[0]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_mutated_test_run_outcome_decides_the_status_2():
    """Scenario: the mutated test run outcome decides the status — example 2"""
    _s = _scenarios[0]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_report_tallies_killed_survived_and_uncovered_0():
    """Scenario: the report tallies killed, survived, and uncovered — example 0"""
    _s = _scenarios[1]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_report_tallies_killed_survived_and_uncovered_1():
    """Scenario: the report tallies killed, survived, and uncovered — example 1"""
    _s = _scenarios[1]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_report_tallies_killed_survived_and_uncovered_2():
    """Scenario: the report tallies killed, survived, and uncovered — example 2"""
    _s = _scenarios[1]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_per_mutant_progress_line_is_the_verbatim_upstream_format_0():
    """Scenario: the per-mutant progress line is the verbatim upstream format — example 0"""
    _s = _scenarios[2]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_mutant_timeout_is_derived_from_the_baseline_duration_0():
    """Scenario: the mutant timeout is derived from the baseline duration — example 0"""
    _s = _scenarios[3]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_mutant_timeout_is_derived_from_the_baseline_duration_1():
    """Scenario: the mutant timeout is derived from the baseline duration — example 1"""
    _s = _scenarios[3]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_failing_baseline_aborts_with_no_mutant_applied_and_no_back_0():
    """Scenario: a failing baseline aborts with no mutant applied and no backup — example 0"""
    _s = _scenarios[4]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_effectivesincelastrun_decides_which_covered_sites_are_select_0():
    """Scenario: effectiveSinceLastRun decides which covered sites are selected — example 0"""
    _s = _scenarios[5]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_effectivesincelastrun_decides_which_covered_sites_are_select_1():
    """Scenario: effectiveSinceLastRun decides which covered sites are selected — example 1"""
    _s = _scenarios[5]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_effectivesincelastrun_decides_which_covered_sites_are_select_2():
    """Scenario: effectiveSinceLastRun decides which covered sites are selected — example 2"""
    _s = _scenarios[5]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_effectivesincelastrun_decides_which_covered_sites_are_select_3():
    """Scenario: effectiveSinceLastRun decides which covered sites are selected — example 3"""
    _s = _scenarios[5]
    _ex = _s['examples'][3] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_uncovered_block_visibility_follows_the_differential_swit_0():
    """Scenario: the uncovered block visibility follows the differential switch — example 0"""
    _s = _scenarios[6]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_uncovered_block_visibility_follows_the_differential_swit_1():
    """Scenario: the uncovered block visibility follows the differential switch — example 1"""
    _s = _scenarios[6]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_uncovered_block_visibility_follows_the_differential_swit_2():
    """Scenario: the uncovered block visibility follows the differential switch — example 2"""
    _s = _scenarios[6]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_uncovered_block_visibility_follows_the_differential_swit_3():
    """Scenario: the uncovered block visibility follows the differential switch — example 3"""
    _s = _scenarios[6]
    _ex = _s['examples'][3] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_run_header_prints_the_count_lines_and_never_a_workers_li_0():
    """Scenario: the run header prints the count lines and never a workers line — example 0"""
    _s = _scenarios[7]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_over_threshold_warning_is_conditional_0():
    """Scenario: the over-threshold warning is conditional — example 0"""
    _s = _scenarios[8]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_over_threshold_warning_is_conditional_1():
    """Scenario: the over-threshold warning is conditional — example 1"""
    _s = _scenarios[8]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_run_restores_the_source_and_re_embeds_the_manifest_0():
    """Scenario: the run restores the source and re-embeds the manifest — example 0"""
    _s = _scenarios[9]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_pre_existing_backup_is_restored_at_the_start_of_the_next_r_0():
    """Scenario: a pre-existing backup is restored at the start of the next run — example 0"""
    _s = _scenarios[10]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_reusing_coverage_warns_that_the_classification_may_be_stale_0():
    """Scenario: reusing coverage warns that the classification may be stale — example 0"""
    _s = _scenarios[11]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

if __name__ == '__main__':
    import traceback
    passed = failed = 0
    try:
        test_the_mutated_test_run_outcome_decides_the_status_0()
        print('PASS test_the_mutated_test_run_outcome_decides_the_status_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_mutated_test_run_outcome_decides_the_status_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_mutated_test_run_outcome_decides_the_status_1()
        print('PASS test_the_mutated_test_run_outcome_decides_the_status_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_mutated_test_run_outcome_decides_the_status_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_mutated_test_run_outcome_decides_the_status_2()
        print('PASS test_the_mutated_test_run_outcome_decides_the_status_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_mutated_test_run_outcome_decides_the_status_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_report_tallies_killed_survived_and_uncovered_0()
        print('PASS test_the_report_tallies_killed_survived_and_uncovered_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_report_tallies_killed_survived_and_uncovered_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_report_tallies_killed_survived_and_uncovered_1()
        print('PASS test_the_report_tallies_killed_survived_and_uncovered_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_report_tallies_killed_survived_and_uncovered_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_report_tallies_killed_survived_and_uncovered_2()
        print('PASS test_the_report_tallies_killed_survived_and_uncovered_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_report_tallies_killed_survived_and_uncovered_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_per_mutant_progress_line_is_the_verbatim_upstream_format_0()
        print('PASS test_the_per_mutant_progress_line_is_the_verbatim_upstream_format_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_per_mutant_progress_line_is_the_verbatim_upstream_format_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_mutant_timeout_is_derived_from_the_baseline_duration_0()
        print('PASS test_the_mutant_timeout_is_derived_from_the_baseline_duration_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_mutant_timeout_is_derived_from_the_baseline_duration_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_mutant_timeout_is_derived_from_the_baseline_duration_1()
        print('PASS test_the_mutant_timeout_is_derived_from_the_baseline_duration_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_mutant_timeout_is_derived_from_the_baseline_duration_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_failing_baseline_aborts_with_no_mutant_applied_and_no_back_0()
        print('PASS test_a_failing_baseline_aborts_with_no_mutant_applied_and_no_back_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_failing_baseline_aborts_with_no_mutant_applied_and_no_back_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_effectivesincelastrun_decides_which_covered_sites_are_select_0()
        print('PASS test_effectivesincelastrun_decides_which_covered_sites_are_select_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_effectivesincelastrun_decides_which_covered_sites_are_select_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_effectivesincelastrun_decides_which_covered_sites_are_select_1()
        print('PASS test_effectivesincelastrun_decides_which_covered_sites_are_select_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_effectivesincelastrun_decides_which_covered_sites_are_select_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_effectivesincelastrun_decides_which_covered_sites_are_select_2()
        print('PASS test_effectivesincelastrun_decides_which_covered_sites_are_select_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_effectivesincelastrun_decides_which_covered_sites_are_select_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_effectivesincelastrun_decides_which_covered_sites_are_select_3()
        print('PASS test_effectivesincelastrun_decides_which_covered_sites_are_select_3')
        passed += 1
    except Exception as e:
        print(f'FAIL test_effectivesincelastrun_decides_which_covered_sites_are_select_3: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_uncovered_block_visibility_follows_the_differential_swit_0()
        print('PASS test_the_uncovered_block_visibility_follows_the_differential_swit_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_uncovered_block_visibility_follows_the_differential_swit_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_uncovered_block_visibility_follows_the_differential_swit_1()
        print('PASS test_the_uncovered_block_visibility_follows_the_differential_swit_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_uncovered_block_visibility_follows_the_differential_swit_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_uncovered_block_visibility_follows_the_differential_swit_2()
        print('PASS test_the_uncovered_block_visibility_follows_the_differential_swit_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_uncovered_block_visibility_follows_the_differential_swit_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_uncovered_block_visibility_follows_the_differential_swit_3()
        print('PASS test_the_uncovered_block_visibility_follows_the_differential_swit_3')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_uncovered_block_visibility_follows_the_differential_swit_3: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_run_header_prints_the_count_lines_and_never_a_workers_li_0()
        print('PASS test_the_run_header_prints_the_count_lines_and_never_a_workers_li_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_run_header_prints_the_count_lines_and_never_a_workers_li_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_over_threshold_warning_is_conditional_0()
        print('PASS test_the_over_threshold_warning_is_conditional_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_over_threshold_warning_is_conditional_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_over_threshold_warning_is_conditional_1()
        print('PASS test_the_over_threshold_warning_is_conditional_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_over_threshold_warning_is_conditional_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_run_restores_the_source_and_re_embeds_the_manifest_0()
        print('PASS test_the_run_restores_the_source_and_re_embeds_the_manifest_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_run_restores_the_source_and_re_embeds_the_manifest_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_pre_existing_backup_is_restored_at_the_start_of_the_next_r_0()
        print('PASS test_a_pre_existing_backup_is_restored_at_the_start_of_the_next_r_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_pre_existing_backup_is_restored_at_the_start_of_the_next_r_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_reusing_coverage_warns_that_the_classification_may_be_stale_0()
        print('PASS test_reusing_coverage_warns_that_the_classification_may_be_stale_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_reusing_coverage_warns_that_the_classification_may_be_stale_0: {e}')
        traceback.print_exc()
        failed += 1
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)
