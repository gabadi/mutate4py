import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from acceptance.steps.site_discovery_qa_steps import run_step

# Scenario data baked in; APS_FEATURE_JSON overrides for gherkin mutation
_aps_override = os.environ.get('APS_FEATURE_JSON')
if _aps_override:
    with open(_aps_override) as _f:
        _ir = json.load(_f)
    _background = _ir.get('background', [])
    _scenarios = _ir.get('scenarios', [])
else:
    _background = [{'keyword': 'Given', 'text': 'the mutate4py command-line tool is installed'}, {'keyword': 'And', 'text': 'a committed Python fixture whose header states its expected total sites'}]
    _scenarios = [{'name': 'scanning a fixture reports its expected total sites', 'steps': [{'keyword': 'Given', 'text': 'a fixture "<fixture>" with expected total <total>', 'parameters': ['fixture', 'total']}, {'keyword': 'When', 'text': 'the command "mutate4py <fixture> --scan" is run', 'parameters': ['fixture']}, {'keyword': 'Then', 'text': 'the command exits successfully'}, {'keyword': 'And', 'text': 'the output line "Mutation scan: <fixture>" is printed', 'parameters': ['fixture']}, {'keyword': 'And', 'text': 'the output line "Total mutation sites: <total>" is printed', 'parameters': ['total']}], 'examples': [{'fixture': 'mixed_operators.py', 'total': '6'}, {'fixture': 'module_level.py', 'total': '2'}, {'fixture': 'empty_units.py', 'total': '0'}]}, {'name': 'a fixture with no manifest reports changed equal to total', 'steps': [{'keyword': 'Given', 'text': 'a fixture "mixed_operators.py" with expected total 6'}, {'keyword': 'When', 'text': 'the command "mutate4py mixed_operators.py --scan" is run'}, {'keyword': 'Then', 'text': 'the output line "Changed mutation sites: 6" is printed'}, {'keyword': 'And', 'text': 'the output line "Manifest exists: false" is printed'}], 'examples': []}, {'name': 'scanning leaves the fixture unchanged and runs no tests', 'steps': [{'keyword': 'Given', 'text': 'a fixture "mixed_operators.py"'}, {'keyword': 'And', 'text': 'a recorded copy of its contents'}, {'keyword': 'When', 'text': 'the command "mixed_operators.py --scan" is run through mutate4py'}, {'keyword': 'Then', 'text': 'the fixture contents on disk match the recorded copy exactly'}, {'keyword': 'And', 'text': 'no test command was executed'}], 'examples': []}, {'name': 'the warning line is shown only when the total exceeds the threshold', 'steps': [{'keyword': 'Given', 'text': 'a fixture "<fixture>" with expected total <total>', 'parameters': ['fixture', 'total']}, {'keyword': 'When', 'text': 'the command "mutate4py <fixture> --scan --mutation-warning <threshold>" is run', 'parameters': ['fixture', 'threshold']}, {'keyword': 'Then', 'text': 'the warning line shown is "<warning>"', 'parameters': ['warning']}], 'examples': [{'fixture': 'mixed_operators.py', 'total': '6', 'threshold': '6', 'warning': ''}, {'fixture': 'mixed_operators.py', 'total': '6', 'threshold': '5', 'warning': 'Warning: 6 mutation sites exceeds threshold 5.'}]}, {'name': 'scanning a path that does not exist fails as a usage error', 'steps': [{'keyword': 'Given', 'text': 'no file exists at "does_not_exist.py"'}, {'keyword': 'When', 'text': 'the command "mutate4py does_not_exist.py --scan" is run'}, {'keyword': 'Then', 'text': 'the command exits with a non-zero status'}, {'keyword': 'And', 'text': 'no "Mutation scan:" line is printed'}], 'examples': []}, {'name': 'two consecutive scans of the same fixture print identical blocks', 'steps': [{'keyword': 'Given', 'text': 'a fixture "mixed_operators.py"'}, {'keyword': 'When', 'text': 'the command "mutate4py mixed_operators.py --scan" is run twice'}, {'keyword': 'Then', 'text': 'both runs print the same scan block'}], 'examples': []}]

def test_scanning_a_fixture_reports_its_expected_total_sites_0():
    """Scenario: scanning a fixture reports its expected total sites — example 0"""
    _s = _scenarios[0]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_scanning_a_fixture_reports_its_expected_total_sites_1():
    """Scenario: scanning a fixture reports its expected total sites — example 1"""
    _s = _scenarios[0]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_scanning_a_fixture_reports_its_expected_total_sites_2():
    """Scenario: scanning a fixture reports its expected total sites — example 2"""
    _s = _scenarios[0]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_fixture_with_no_manifest_reports_changed_equal_to_total_0():
    """Scenario: a fixture with no manifest reports changed equal to total — example 0"""
    _s = _scenarios[1]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_scanning_leaves_the_fixture_unchanged_and_runs_no_tests_0():
    """Scenario: scanning leaves the fixture unchanged and runs no tests — example 0"""
    _s = _scenarios[2]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_warning_line_is_shown_only_when_the_total_exceeds_the_th_0():
    """Scenario: the warning line is shown only when the total exceeds the threshold — example 0"""
    _s = _scenarios[3]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_warning_line_is_shown_only_when_the_total_exceeds_the_th_1():
    """Scenario: the warning line is shown only when the total exceeds the threshold — example 1"""
    _s = _scenarios[3]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_scanning_a_path_that_does_not_exist_fails_as_a_usage_error_0():
    """Scenario: scanning a path that does not exist fails as a usage error — example 0"""
    _s = _scenarios[4]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_two_consecutive_scans_of_the_same_fixture_print_identical_bl_0():
    """Scenario: two consecutive scans of the same fixture print identical blocks — example 0"""
    _s = _scenarios[5]
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
        test_scanning_a_fixture_reports_its_expected_total_sites_0()
        print('PASS test_scanning_a_fixture_reports_its_expected_total_sites_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_scanning_a_fixture_reports_its_expected_total_sites_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_scanning_a_fixture_reports_its_expected_total_sites_1()
        print('PASS test_scanning_a_fixture_reports_its_expected_total_sites_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_scanning_a_fixture_reports_its_expected_total_sites_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_scanning_a_fixture_reports_its_expected_total_sites_2()
        print('PASS test_scanning_a_fixture_reports_its_expected_total_sites_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_scanning_a_fixture_reports_its_expected_total_sites_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_fixture_with_no_manifest_reports_changed_equal_to_total_0()
        print('PASS test_a_fixture_with_no_manifest_reports_changed_equal_to_total_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_fixture_with_no_manifest_reports_changed_equal_to_total_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_scanning_leaves_the_fixture_unchanged_and_runs_no_tests_0()
        print('PASS test_scanning_leaves_the_fixture_unchanged_and_runs_no_tests_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_scanning_leaves_the_fixture_unchanged_and_runs_no_tests_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_warning_line_is_shown_only_when_the_total_exceeds_the_th_0()
        print('PASS test_the_warning_line_is_shown_only_when_the_total_exceeds_the_th_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_warning_line_is_shown_only_when_the_total_exceeds_the_th_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_warning_line_is_shown_only_when_the_total_exceeds_the_th_1()
        print('PASS test_the_warning_line_is_shown_only_when_the_total_exceeds_the_th_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_warning_line_is_shown_only_when_the_total_exceeds_the_th_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_scanning_a_path_that_does_not_exist_fails_as_a_usage_error_0()
        print('PASS test_scanning_a_path_that_does_not_exist_fails_as_a_usage_error_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_scanning_a_path_that_does_not_exist_fails_as_a_usage_error_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_two_consecutive_scans_of_the_same_fixture_print_identical_bl_0()
        print('PASS test_two_consecutive_scans_of_the_same_fixture_print_identical_bl_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_two_consecutive_scans_of_the_same_fixture_print_identical_bl_0: {e}')
        traceback.print_exc()
        failed += 1
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)
