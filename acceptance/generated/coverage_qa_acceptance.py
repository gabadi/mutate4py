import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from acceptance.steps.coverage_qa_steps import run_step

# Scenario data baked in; APS_FEATURE_JSON overrides for gherkin mutation
_aps_override = os.environ.get('APS_FEATURE_JSON')
if _aps_override:
    with open(_aps_override) as _f:
        _ir = json.load(_f)
    _background = _ir.get('background', [])
    _scenarios = _ir.get('scenarios', [])
else:
    _background = [{'keyword': 'Given', 'text': 'a temp working directory the QA agent owns and tears down'}, {'keyword': 'And', 'text': 'a Python source fixture "calc.py" with exactly one mutation site per line on "3,5,7"'}, {'keyword': 'And', 'text': 'the baseline "mutate4py calc.py --scan" reports "Total mutation sites: 3"'}]
    _scenarios = [{'name': 'QA sees covered/uncovered counts shift with the LCOV DA records', 'steps': [{'keyword': 'Given', 'text': 'a hand-written LCOV "cov.info" with SF matching "calc.py" and DA hits on lines "<covered>"', 'parameters': ['covered']}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --scan --lcov cov.info"'}, {'keyword': 'Then', 'text': 'stdout contains "Total mutation sites: 3"'}, {'keyword': 'And', 'text': 'stdout contains "Covered mutation sites: <coveredCount>"', 'parameters': ['coveredCount']}, {'keyword': 'And', 'text': 'stdout contains "Uncovered mutation sites: <uncoveredCount>"', 'parameters': ['uncoveredCount']}, {'keyword': 'And', 'text': 'the exit status is zero'}], 'examples': [{'covered': '3,5,7', 'coveredCount': '3', 'uncoveredCount': '0'}, {'covered': '3,7', 'coveredCount': '2', 'uncoveredCount': '1'}, {'covered': '', 'coveredCount': '0', 'uncoveredCount': '3'}]}, {'name': 'QA sees a zero-hit DA record counted as uncovered', 'steps': [{'keyword': 'Given', 'text': 'a hand-written LCOV "cov.info" with SF matching "calc.py" and the record "DA:5,0"'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --scan --lcov cov.info"'}, {'keyword': 'Then', 'text': 'stdout contains "Covered mutation sites: 0"'}, {'keyword': 'And', 'text': 'stdout contains "Uncovered mutation sites: 3"'}], 'examples': []}, {'name': 'QA sees branch-only LCOV data ignored by the gate', 'steps': [{'keyword': 'Given', 'text': 'a hand-written LCOV "cov.info" with SF matching "calc.py" containing only "BRDA:5,0,0,1" for line 5'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --scan --lcov cov.info"'}, {'keyword': 'Then', 'text': 'stdout contains "Covered mutation sites: 0"'}, {'keyword': 'And', 'text': 'stdout contains "Uncovered mutation sites: 3"'}], 'examples': []}, {'name': 'QA confirms suffix matching across absolute-vs-relative SF paths', 'steps': [{'keyword': 'Given', 'text': 'a hand-written LCOV "cov.info" whose SF is "<sfPath>" with DA hits on line 5', 'parameters': ['sfPath']}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py <abspath>/calc.py --scan --lcov cov.info"', 'parameters': ['abspath']}, {'keyword': 'Then', 'text': 'stdout contains "Covered mutation sites: <coveredCount>"', 'parameters': ['coveredCount']}], 'examples': [{'sfPath': 'calc.py', 'coveredCount': '1'}, {'sfPath': 'other/elsewhere.py', 'coveredCount': '0'}]}, {'name': 'QA proves --cov-cmd is invoked once via a run-count sentinel', 'steps': [{'keyword': 'Given', 'text': 'a coverage command that appends one byte to "cov-runs.log" and writes "cov.info" with DA hits on line 5'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --scan --cov-cmd \'<that command>\'"'}, {'keyword': 'Then', 'text': 'stdout contains "Covered mutation sites: 1"'}, {'keyword': 'And', 'text': 'the file "cov-runs.log" is exactly one byte'}, {'keyword': 'And', 'text': 'the exit status is zero'}], 'examples': []}, {'name': 'QA confirms --reuse-coverage reads coverage.lcov without regenerating', 'steps': [{'keyword': 'Given', 'text': 'a hand-written LCOV at the default path "coverage.lcov" with SF matching "calc.py" and DA hits on line 5'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --scan --reuse-coverage"'}, {'keyword': 'Then', 'text': 'stdout contains "Covered mutation sites: 1"'}, {'keyword': 'And', 'text': 'no coverage command was run'}], 'examples': []}, {'name': 'QA confirms a missing coverage source exits non-zero and prints no counts', 'steps': [{'keyword': 'Given', 'text': 'there is no readable LCOV at "<missing>"', 'parameters': ['missing']}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --scan <flag>"', 'parameters': ['flag']}, {'keyword': 'Then', 'text': 'the exit status is non-zero'}, {'keyword': 'And', 'text': 'stdout does not contain "Covered mutation sites:"'}, {'keyword': 'And', 'text': 'stdout does not contain "Uncovered mutation sites:"'}], 'examples': [{'flag': '--reuse-coverage', 'missing': 'coverage.lcov'}, {'flag': '--lcov missing.info', 'missing': 'missing.info'}]}, {'name': 'QA confirms more than one coverage flag is a usage error', 'steps': [{'keyword': 'Given', 'text': 'each referenced file in "<flags>" exists so the failure is the exclusivity check', 'parameters': ['flags']}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --scan <flags>"', 'parameters': ['flags']}, {'keyword': 'Then', 'text': 'the exit status is non-zero'}, {'keyword': 'And', 'text': 'stdout does not contain "Covered mutation sites:"'}], 'examples': [{'flags': '--lcov cov.info --reuse-coverage'}, {'flags': '--cov-cmd CMD --lcov cov.info'}, {'flags': '--cov-cmd CMD --reuse-coverage'}]}, {'name': 'QA confirms the source is byte-unchanged and no backup is left', 'steps': [{'keyword': 'Given', 'text': 'the bytes of "calc.py" are recorded before the run'}, {'keyword': 'And', 'text': 'a hand-written LCOV "cov.info" with SF matching "calc.py" and DA hits on lines "3,5,7"'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --scan --lcov cov.info"'}, {'keyword': 'Then', 'text': 'the bytes of "calc.py" are unchanged after the run'}, {'keyword': 'And', 'text': 'no ".mutate4py.bak" file exists in the working directory'}], 'examples': []}]

def test_qa_sees_covered_uncovered_counts_shift_with_the_lcov_da_reco_0():
    """Scenario: QA sees covered/uncovered counts shift with the LCOV DA records — example 0"""
    _s = _scenarios[0]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_sees_covered_uncovered_counts_shift_with_the_lcov_da_reco_1():
    """Scenario: QA sees covered/uncovered counts shift with the LCOV DA records — example 1"""
    _s = _scenarios[0]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_sees_covered_uncovered_counts_shift_with_the_lcov_da_reco_2():
    """Scenario: QA sees covered/uncovered counts shift with the LCOV DA records — example 2"""
    _s = _scenarios[0]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_sees_a_zero_hit_da_record_counted_as_uncovered_0():
    """Scenario: QA sees a zero-hit DA record counted as uncovered — example 0"""
    _s = _scenarios[1]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_sees_branch_only_lcov_data_ignored_by_the_gate_0():
    """Scenario: QA sees branch-only LCOV data ignored by the gate — example 0"""
    _s = _scenarios[2]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_suffix_matching_across_absolute_vs_relative_sf_p_0():
    """Scenario: QA confirms suffix matching across absolute-vs-relative SF paths — example 0"""
    _s = _scenarios[3]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_suffix_matching_across_absolute_vs_relative_sf_p_1():
    """Scenario: QA confirms suffix matching across absolute-vs-relative SF paths — example 1"""
    _s = _scenarios[3]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_proves_cov_cmd_is_invoked_once_via_a_run_count_sentinel_0():
    """Scenario: QA proves --cov-cmd is invoked once via a run-count sentinel — example 0"""
    _s = _scenarios[4]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_reuse_coverage_reads_coverage_lcov_without_regen_0():
    """Scenario: QA confirms --reuse-coverage reads coverage.lcov without regenerating — example 0"""
    _s = _scenarios[5]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_a_missing_coverage_source_exits_non_zero_and_pri_0():
    """Scenario: QA confirms a missing coverage source exits non-zero and prints no counts — example 0"""
    _s = _scenarios[6]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_a_missing_coverage_source_exits_non_zero_and_pri_1():
    """Scenario: QA confirms a missing coverage source exits non-zero and prints no counts — example 1"""
    _s = _scenarios[6]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_more_than_one_coverage_flag_is_a_usage_error_0():
    """Scenario: QA confirms more than one coverage flag is a usage error — example 0"""
    _s = _scenarios[7]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_more_than_one_coverage_flag_is_a_usage_error_1():
    """Scenario: QA confirms more than one coverage flag is a usage error — example 1"""
    _s = _scenarios[7]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_more_than_one_coverage_flag_is_a_usage_error_2():
    """Scenario: QA confirms more than one coverage flag is a usage error — example 2"""
    _s = _scenarios[7]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_the_source_is_byte_unchanged_and_no_backup_is_le_0():
    """Scenario: QA confirms the source is byte-unchanged and no backup is left — example 0"""
    _s = _scenarios[8]
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
        test_qa_sees_covered_uncovered_counts_shift_with_the_lcov_da_reco_0()
        print('PASS test_qa_sees_covered_uncovered_counts_shift_with_the_lcov_da_reco_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_sees_covered_uncovered_counts_shift_with_the_lcov_da_reco_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_sees_covered_uncovered_counts_shift_with_the_lcov_da_reco_1()
        print('PASS test_qa_sees_covered_uncovered_counts_shift_with_the_lcov_da_reco_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_sees_covered_uncovered_counts_shift_with_the_lcov_da_reco_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_sees_covered_uncovered_counts_shift_with_the_lcov_da_reco_2()
        print('PASS test_qa_sees_covered_uncovered_counts_shift_with_the_lcov_da_reco_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_sees_covered_uncovered_counts_shift_with_the_lcov_da_reco_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_sees_a_zero_hit_da_record_counted_as_uncovered_0()
        print('PASS test_qa_sees_a_zero_hit_da_record_counted_as_uncovered_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_sees_a_zero_hit_da_record_counted_as_uncovered_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_sees_branch_only_lcov_data_ignored_by_the_gate_0()
        print('PASS test_qa_sees_branch_only_lcov_data_ignored_by_the_gate_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_sees_branch_only_lcov_data_ignored_by_the_gate_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_suffix_matching_across_absolute_vs_relative_sf_p_0()
        print('PASS test_qa_confirms_suffix_matching_across_absolute_vs_relative_sf_p_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_suffix_matching_across_absolute_vs_relative_sf_p_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_suffix_matching_across_absolute_vs_relative_sf_p_1()
        print('PASS test_qa_confirms_suffix_matching_across_absolute_vs_relative_sf_p_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_suffix_matching_across_absolute_vs_relative_sf_p_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_proves_cov_cmd_is_invoked_once_via_a_run_count_sentinel_0()
        print('PASS test_qa_proves_cov_cmd_is_invoked_once_via_a_run_count_sentinel_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_proves_cov_cmd_is_invoked_once_via_a_run_count_sentinel_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_reuse_coverage_reads_coverage_lcov_without_regen_0()
        print('PASS test_qa_confirms_reuse_coverage_reads_coverage_lcov_without_regen_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_reuse_coverage_reads_coverage_lcov_without_regen_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_a_missing_coverage_source_exits_non_zero_and_pri_0()
        print('PASS test_qa_confirms_a_missing_coverage_source_exits_non_zero_and_pri_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_a_missing_coverage_source_exits_non_zero_and_pri_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_a_missing_coverage_source_exits_non_zero_and_pri_1()
        print('PASS test_qa_confirms_a_missing_coverage_source_exits_non_zero_and_pri_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_a_missing_coverage_source_exits_non_zero_and_pri_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_more_than_one_coverage_flag_is_a_usage_error_0()
        print('PASS test_qa_confirms_more_than_one_coverage_flag_is_a_usage_error_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_more_than_one_coverage_flag_is_a_usage_error_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_more_than_one_coverage_flag_is_a_usage_error_1()
        print('PASS test_qa_confirms_more_than_one_coverage_flag_is_a_usage_error_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_more_than_one_coverage_flag_is_a_usage_error_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_more_than_one_coverage_flag_is_a_usage_error_2()
        print('PASS test_qa_confirms_more_than_one_coverage_flag_is_a_usage_error_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_more_than_one_coverage_flag_is_a_usage_error_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_the_source_is_byte_unchanged_and_no_backup_is_le_0()
        print('PASS test_qa_confirms_the_source_is_byte_unchanged_and_no_backup_is_le_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_the_source_is_byte_unchanged_and_no_backup_is_le_0: {e}')
        traceback.print_exc()
        failed += 1
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)
