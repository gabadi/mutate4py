import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from acceptance.steps.run_loop_qa_steps import run_step

# Scenario data baked in; APS_FEATURE_JSON overrides for gherkin mutation
_aps_override = os.environ.get('APS_FEATURE_JSON')
if _aps_override:
    with open(_aps_override) as _f:
        _ir = json.load(_f)
    _background = _ir.get('background', [])
    _scenarios = _ir.get('scenarios', [])
else:
    _background = [{'keyword': 'Given', 'text': 'a temp working directory the QA agent owns and tears down'}, {'keyword': 'And', 'text': 'a Python source fixture "calc.py" with covered mutation sites on lines "3,7"'}, {'keyword': 'And', 'text': 'a hand-written LCOV "cov.info" with SF matching "calc.py" and DA hits on lines "3,7"'}, {'keyword': 'And', 'text': 'a fake test command "runtests.sh" the QA agent scripts per outcome'}]
    _scenarios = [{'name': 'QA drives killed / survived / timeout and sees the status verbatim', 'steps': [{'keyword': 'Given', 'text': '"runtests.sh" makes the mutated run "<outcome>" while the baseline passes', 'parameters': ['outcome']}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --lcov cov.info --test-command ./runtests.sh --timeout-factor 2"'}, {'keyword': 'Then', 'text': 'stdout contains a line matching "[<n>/<total>] <status> line " for that mutant', 'parameters': ['n', 'total', 'status']}, {'keyword': 'And', 'text': 'the exit status is zero'}], 'examples': [{'outcome': 'exit nonzero', 'status': 'killed'}, {'outcome': 'exit zero', 'status': 'survived'}, {'outcome': 'sleep past timeout', 'status': 'timeout'}]}, {'name': 'QA sees a timed-out mutant counted as Killed, not as a Timeout line', 'steps': [{'keyword': 'Given', 'text': '"runtests.sh" makes one mutant sleep past the timeout and the rest exit nonzero'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --lcov cov.info --test-command ./runtests.sh --timeout-factor 2"'}, {'keyword': 'Then', 'text': 'stdout contains "timeout line "'}, {'keyword': 'And', 'text': 'stdout contains "Killed: 2"'}, {'keyword': 'And', 'text': 'stdout does not contain "Timeout:"'}], 'examples': []}, {'name': 'QA confirms the Survivors block is conditional on survived > 0', 'steps': [{'keyword': 'Given', 'text': '"runtests.sh" makes "<survivedCount>" of the 2 mutants exit zero and the rest exit nonzero', 'parameters': ['survivedCount']}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --lcov cov.info --test-command ./runtests.sh --timeout-factor 2"'}, {'keyword': 'Then', 'text': 'stdout contains "Survived: <survivedCount>"', 'parameters': ['survivedCount']}, {'keyword': 'And', 'text': 'stdout "<containsSurvivors>" contain "Survivors:"', 'parameters': ['containsSurvivors']}], 'examples': [{'survivedCount': '0', 'containsSurvivors': 'does not'}, {'survivedCount': '1', 'containsSurvivors': 'does'}]}, {'name': 'QA sees a failing baseline abort the run with no report and no backup', 'steps': [{'keyword': 'Given', 'text': '"runtests.sh" exits nonzero on the unmutated baseline run'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --lcov cov.info --test-command ./runtests.sh"'}, {'keyword': 'Then', 'text': 'the exit status is non-zero'}, {'keyword': 'And', 'text': 'stdout contains "baseline failed:"'}, {'keyword': 'And', 'text': 'stdout does not contain "Mutation Report"'}, {'keyword': 'And', 'text': 'no ".mutate4py.bak" file exists in the working directory'}], 'examples': []}, {'name': 'QA confirms the run header lines are present and no workers line appears', 'steps': [{'keyword': 'Given', 'text': '"runtests.sh" exits nonzero for every mutant'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --lcov cov.info --test-command ./runtests.sh --timeout-factor 2"'}, {'keyword': 'Then', 'text': 'stdout contains "Mutation run: calc.py"'}, {'keyword': 'And', 'text': 'stdout contains "Total mutation sites:"'}, {'keyword': 'And', 'text': 'stdout contains "Selected mutation sites:"'}, {'keyword': 'And', 'text': 'stdout does not contain "Mutation workers:"'}, {'keyword': 'And', 'text': 'stdout does not contain "worker-"'}], 'examples': []}, {'name': 'QA confirms the source is byte-restored with a fresh manifest after the run', 'steps': [{'keyword': 'Given', 'text': 'the bytes of "calc.py" before any manifest footer are recorded'}, {'keyword': 'And', 'text': '"runtests.sh" exits nonzero for every mutant'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --lcov cov.info --test-command ./runtests.sh --timeout-factor 2"'}, {'keyword': 'Then', 'text': 'the body of "calc.py" above the manifest footer is unchanged'}, {'keyword': 'And', 'text': '"calc.py" ends with a "mutate4py-manifest-begin" / "mutate4py-manifest-end" footer'}, {'keyword': 'And', 'text': 'no ".mutate4py.bak" file exists in the working directory'}], 'examples': []}, {'name': 'QA confirms a leftover backup is restored and announced on the next run', 'steps': [{'keyword': 'Given', 'text': 'a ".mutate4py.bak" file holding a known prior source body exists in the working directory'}, {'keyword': 'And', 'text': '"calc.py" on disk currently holds a leftover spliced mutant'}, {'keyword': 'And', 'text': '"runtests.sh" exits nonzero for every mutant'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --lcov cov.info --test-command ./runtests.sh --timeout-factor 2"'}, {'keyword': 'Then', 'text': 'stdout contains "Restored source from backup (previous run was interrupted)."'}, {'keyword': 'And', 'text': 'the body of "calc.py" above the manifest footer matches the prior source body'}], 'examples': []}, {'name': 'QA sees the stale-coverage warning printed before the run header', 'steps': [{'keyword': 'Given', 'text': 'a hand-written LCOV at the default path "coverage.lcov" with DA hits on lines "3,7"'}, {'keyword': 'And', 'text': '"runtests.sh" exits nonzero for every mutant'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --reuse-coverage --test-command ./runtests.sh --timeout-factor 2"'}, {'keyword': 'Then', 'text': 'stdout contains "Reusing existing coverage; covered/uncovered classification may be stale."'}, {'keyword': 'And', 'text': 'that line appears before "Mutation run: calc.py" in stdout'}], 'examples': []}]

def test_qa_drives_killed_survived_timeout_and_sees_the_status_verbat_0():
    """Scenario: QA drives killed / survived / timeout and sees the status verbatim — example 0"""
    _s = _scenarios[0]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_drives_killed_survived_timeout_and_sees_the_status_verbat_1():
    """Scenario: QA drives killed / survived / timeout and sees the status verbatim — example 1"""
    _s = _scenarios[0]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_drives_killed_survived_timeout_and_sees_the_status_verbat_2():
    """Scenario: QA drives killed / survived / timeout and sees the status verbatim — example 2"""
    _s = _scenarios[0]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_sees_a_timed_out_mutant_counted_as_killed_not_as_a_timeou_0():
    """Scenario: QA sees a timed-out mutant counted as Killed, not as a Timeout line — example 0"""
    _s = _scenarios[1]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_the_survivors_block_is_conditional_on_survived_0_0():
    """Scenario: QA confirms the Survivors block is conditional on survived > 0 — example 0"""
    _s = _scenarios[2]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_the_survivors_block_is_conditional_on_survived_0_1():
    """Scenario: QA confirms the Survivors block is conditional on survived > 0 — example 1"""
    _s = _scenarios[2]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_sees_a_failing_baseline_abort_the_run_with_no_report_and__0():
    """Scenario: QA sees a failing baseline abort the run with no report and no backup — example 0"""
    _s = _scenarios[3]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_the_run_header_lines_are_present_and_no_workers__0():
    """Scenario: QA confirms the run header lines are present and no workers line appears — example 0"""
    _s = _scenarios[4]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_the_source_is_byte_restored_with_a_fresh_manifes_0():
    """Scenario: QA confirms the source is byte-restored with a fresh manifest after the run — example 0"""
    _s = _scenarios[5]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_a_leftover_backup_is_restored_and_announced_on_t_0():
    """Scenario: QA confirms a leftover backup is restored and announced on the next run — example 0"""
    _s = _scenarios[6]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_sees_the_stale_coverage_warning_printed_before_the_run_he_0():
    """Scenario: QA sees the stale-coverage warning printed before the run header — example 0"""
    _s = _scenarios[7]
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
        test_qa_drives_killed_survived_timeout_and_sees_the_status_verbat_0()
        print('PASS test_qa_drives_killed_survived_timeout_and_sees_the_status_verbat_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_drives_killed_survived_timeout_and_sees_the_status_verbat_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_drives_killed_survived_timeout_and_sees_the_status_verbat_1()
        print('PASS test_qa_drives_killed_survived_timeout_and_sees_the_status_verbat_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_drives_killed_survived_timeout_and_sees_the_status_verbat_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_drives_killed_survived_timeout_and_sees_the_status_verbat_2()
        print('PASS test_qa_drives_killed_survived_timeout_and_sees_the_status_verbat_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_drives_killed_survived_timeout_and_sees_the_status_verbat_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_sees_a_timed_out_mutant_counted_as_killed_not_as_a_timeou_0()
        print('PASS test_qa_sees_a_timed_out_mutant_counted_as_killed_not_as_a_timeou_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_sees_a_timed_out_mutant_counted_as_killed_not_as_a_timeou_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_the_survivors_block_is_conditional_on_survived_0_0()
        print('PASS test_qa_confirms_the_survivors_block_is_conditional_on_survived_0_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_the_survivors_block_is_conditional_on_survived_0_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_the_survivors_block_is_conditional_on_survived_0_1()
        print('PASS test_qa_confirms_the_survivors_block_is_conditional_on_survived_0_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_the_survivors_block_is_conditional_on_survived_0_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_sees_a_failing_baseline_abort_the_run_with_no_report_and__0()
        print('PASS test_qa_sees_a_failing_baseline_abort_the_run_with_no_report_and__0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_sees_a_failing_baseline_abort_the_run_with_no_report_and__0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_the_run_header_lines_are_present_and_no_workers__0()
        print('PASS test_qa_confirms_the_run_header_lines_are_present_and_no_workers__0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_the_run_header_lines_are_present_and_no_workers__0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_the_source_is_byte_restored_with_a_fresh_manifes_0()
        print('PASS test_qa_confirms_the_source_is_byte_restored_with_a_fresh_manifes_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_the_source_is_byte_restored_with_a_fresh_manifes_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_a_leftover_backup_is_restored_and_announced_on_t_0()
        print('PASS test_qa_confirms_a_leftover_backup_is_restored_and_announced_on_t_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_a_leftover_backup_is_restored_and_announced_on_t_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_sees_the_stale_coverage_warning_printed_before_the_run_he_0()
        print('PASS test_qa_sees_the_stale_coverage_warning_printed_before_the_run_he_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_sees_the_stale_coverage_warning_printed_before_the_run_he_0: {e}')
        traceback.print_exc()
        failed += 1
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)
