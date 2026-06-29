import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from acceptance.steps.coverage_steps import run_step

# Scenario data baked in; APS_FEATURE_JSON overrides for gherkin mutation
_aps_override = os.environ.get('APS_FEATURE_JSON')
if _aps_override:
    with open(_aps_override) as _f:
        _ir = json.load(_f)
    _background = _ir.get('background', [])
    _scenarios = _ir.get('scenarios', [])
else:
    _background = [{'keyword': 'Given', 'text': 'a Python source file with mutation sites on lines "3,5,7"'}]
    _scenarios = [{'name': 'a site is covered iff its line has a positive DA count', 'steps': [{'keyword': 'Given', 'text': 'an LCOV file covering lines "<covered>" for that source', 'parameters': ['covered']}, {'keyword': 'When', 'text': 'I run mutate4py scanning with coverage "--lcov cov.info"'}, {'keyword': 'Then', 'text': 'the output line "Total mutation sites: 3" is printed'}, {'keyword': 'And', 'text': 'the output line "Covered mutation sites: <coveredCount>" is printed', 'parameters': ['coveredCount']}, {'keyword': 'And', 'text': 'the output line "Uncovered mutation sites: <uncoveredCount>" is printed', 'parameters': ['uncoveredCount']}], 'examples': [{'covered': '3,5,7', 'coveredCount': '3', 'uncoveredCount': '0'}, {'covered': '3,7', 'coveredCount': '2', 'uncoveredCount': '1'}, {'covered': '', 'coveredCount': '0', 'uncoveredCount': '3'}]}, {'name': 'a DA count of zero is uncovered, not covered', 'steps': [{'keyword': 'Given', 'text': 'an LCOV file with the single record "DA:5,0" for that source'}, {'keyword': 'When', 'text': 'I run mutate4py scanning with coverage "--lcov cov.info"'}, {'keyword': 'Then', 'text': 'the output line "Covered mutation sites: 0" is printed'}, {'keyword': 'And', 'text': 'the output line "Uncovered mutation sites: 3" is printed'}], 'examples': []}, {'name': 'a line with only branch data and no positive DA hit is uncovered', 'steps': [{'keyword': 'Given', 'text': 'an LCOV file whose only record for line 5 is branch data "BRDA:5,0,0,1"'}, {'keyword': 'When', 'text': 'I run mutate4py scanning with coverage "--lcov cov.info"'}, {'keyword': 'Then', 'text': 'the output line "Covered mutation sites: 0" is printed'}, {'keyword': 'And', 'text': 'the output line "Uncovered mutation sites: 3" is printed'}], 'examples': []}, {'name': 'an LCOV SF path matches the target by suffix', 'steps': [{'keyword': 'Given', 'text': 'an LCOV file covering line 5 under the SF path "<sfPath>" for that source', 'parameters': ['sfPath']}, {'keyword': 'When', 'text': 'I run mutate4py scanning with coverage "--lcov cov.info"'}, {'keyword': 'Then', 'text': 'the output line "Covered mutation sites: <coveredCount>" is printed', 'parameters': ['coveredCount']}], 'examples': [{'sfPath': 'absolute-suffix', 'coveredCount': '1'}, {'sfPath': 'relative-suffix', 'coveredCount': '1'}, {'sfPath': 'unrelated-file', 'coveredCount': '0'}]}, {'name': '--cov-cmd is run exactly once to acquire coverage', 'steps': [{'keyword': 'Given', 'text': 'a coverage command that emits an LCOV file covering line 5'}, {'keyword': 'When', 'text': 'I run mutate4py scanning with coverage "--cov-cmd CMD"'}, {'keyword': 'Then', 'text': 'the coverage command runs exactly once'}, {'keyword': 'And', 'text': 'the output line "Covered mutation sites: 1" is printed'}], 'examples': []}, {'name': '--reuse-coverage reads coverage.lcov without regenerating', 'steps': [{'keyword': 'Given', 'text': 'an LCOV file at the default path "coverage.lcov" covering lines "5" for that source'}, {'keyword': 'When', 'text': 'I run mutate4py scanning with coverage "--reuse-coverage"'}, {'keyword': 'Then', 'text': 'the output line "Covered mutation sites: 1" is printed'}, {'keyword': 'And', 'text': 'the coverage command runs exactly 0 times'}], 'examples': []}, {'name': 'a missing or unusable coverage source exits non-zero and prints no counts', 'steps': [{'keyword': 'Given', 'text': 'there is no readable LCOV at "<missing>"', 'parameters': ['missing']}, {'keyword': 'When', 'text': 'I run mutate4py scanning with coverage "<flag>"', 'parameters': ['flag']}, {'keyword': 'Then', 'text': 'the command exits with a non-zero status'}, {'keyword': 'And', 'text': 'no partition counts are printed'}], 'examples': [{'flag': '--reuse-coverage', 'missing': 'coverage.lcov'}, {'flag': '--lcov missing.info', 'missing': 'missing.info'}]}, {'name': 'supplying more than one coverage flag is a usage error', 'steps': [{'keyword': 'When', 'text': 'I run mutate4py scanning with coverage "<flags>"', 'parameters': ['flags']}, {'keyword': 'Then', 'text': 'the command exits with a non-zero status'}, {'keyword': 'And', 'text': 'no partition counts are printed'}], 'examples': [{'flags': '--lcov cov.info --reuse-coverage'}, {'flags': '--cov-cmd CMD --lcov cov.info'}, {'flags': '--cov-cmd CMD --reuse-coverage'}]}, {'name': 'scanning with coverage leaves the source byte-identical and no backup', 'steps': [{'keyword': 'Given', 'text': 'an LCOV file covering lines "3,5,7" for that source'}, {'keyword': 'When', 'text': 'I run mutate4py scanning with coverage "--lcov cov.info"'}, {'keyword': 'Then', 'text': 'the source file is byte-for-byte unchanged'}, {'keyword': 'And', 'text': 'no ".mutate4py.bak" file is left behind'}], 'examples': []}]

def test_a_site_is_covered_iff_its_line_has_a_positive_da_count_0():
    """Scenario: a site is covered iff its line has a positive DA count — example 0"""
    _s = _scenarios[0]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_site_is_covered_iff_its_line_has_a_positive_da_count_1():
    """Scenario: a site is covered iff its line has a positive DA count — example 1"""
    _s = _scenarios[0]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_site_is_covered_iff_its_line_has_a_positive_da_count_2():
    """Scenario: a site is covered iff its line has a positive DA count — example 2"""
    _s = _scenarios[0]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_da_count_of_zero_is_uncovered_not_covered_0():
    """Scenario: a DA count of zero is uncovered, not covered — example 0"""
    _s = _scenarios[1]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_line_with_only_branch_data_and_no_positive_da_hit_is_uncov_0():
    """Scenario: a line with only branch data and no positive DA hit is uncovered — example 0"""
    _s = _scenarios[2]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_an_lcov_sf_path_matches_the_target_by_suffix_0():
    """Scenario: an LCOV SF path matches the target by suffix — example 0"""
    _s = _scenarios[3]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_an_lcov_sf_path_matches_the_target_by_suffix_1():
    """Scenario: an LCOV SF path matches the target by suffix — example 1"""
    _s = _scenarios[3]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_an_lcov_sf_path_matches_the_target_by_suffix_2():
    """Scenario: an LCOV SF path matches the target by suffix — example 2"""
    _s = _scenarios[3]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_cov_cmd_is_run_exactly_once_to_acquire_coverage_0():
    """Scenario: --cov-cmd is run exactly once to acquire coverage — example 0"""
    _s = _scenarios[4]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_reuse_coverage_reads_coverage_lcov_without_regenerating_0():
    """Scenario: --reuse-coverage reads coverage.lcov without regenerating — example 0"""
    _s = _scenarios[5]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_missing_or_unusable_coverage_source_exits_non_zero_and_pri_0():
    """Scenario: a missing or unusable coverage source exits non-zero and prints no counts — example 0"""
    _s = _scenarios[6]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_missing_or_unusable_coverage_source_exits_non_zero_and_pri_1():
    """Scenario: a missing or unusable coverage source exits non-zero and prints no counts — example 1"""
    _s = _scenarios[6]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_supplying_more_than_one_coverage_flag_is_a_usage_error_0():
    """Scenario: supplying more than one coverage flag is a usage error — example 0"""
    _s = _scenarios[7]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_supplying_more_than_one_coverage_flag_is_a_usage_error_1():
    """Scenario: supplying more than one coverage flag is a usage error — example 1"""
    _s = _scenarios[7]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_supplying_more_than_one_coverage_flag_is_a_usage_error_2():
    """Scenario: supplying more than one coverage flag is a usage error — example 2"""
    _s = _scenarios[7]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_scanning_with_coverage_leaves_the_source_byte_identical_and__0():
    """Scenario: scanning with coverage leaves the source byte-identical and no backup — example 0"""
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
        test_a_site_is_covered_iff_its_line_has_a_positive_da_count_0()
        print('PASS test_a_site_is_covered_iff_its_line_has_a_positive_da_count_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_site_is_covered_iff_its_line_has_a_positive_da_count_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_site_is_covered_iff_its_line_has_a_positive_da_count_1()
        print('PASS test_a_site_is_covered_iff_its_line_has_a_positive_da_count_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_site_is_covered_iff_its_line_has_a_positive_da_count_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_site_is_covered_iff_its_line_has_a_positive_da_count_2()
        print('PASS test_a_site_is_covered_iff_its_line_has_a_positive_da_count_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_site_is_covered_iff_its_line_has_a_positive_da_count_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_da_count_of_zero_is_uncovered_not_covered_0()
        print('PASS test_a_da_count_of_zero_is_uncovered_not_covered_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_da_count_of_zero_is_uncovered_not_covered_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_line_with_only_branch_data_and_no_positive_da_hit_is_uncov_0()
        print('PASS test_a_line_with_only_branch_data_and_no_positive_da_hit_is_uncov_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_line_with_only_branch_data_and_no_positive_da_hit_is_uncov_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_an_lcov_sf_path_matches_the_target_by_suffix_0()
        print('PASS test_an_lcov_sf_path_matches_the_target_by_suffix_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_an_lcov_sf_path_matches_the_target_by_suffix_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_an_lcov_sf_path_matches_the_target_by_suffix_1()
        print('PASS test_an_lcov_sf_path_matches_the_target_by_suffix_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_an_lcov_sf_path_matches_the_target_by_suffix_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_an_lcov_sf_path_matches_the_target_by_suffix_2()
        print('PASS test_an_lcov_sf_path_matches_the_target_by_suffix_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_an_lcov_sf_path_matches_the_target_by_suffix_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_cov_cmd_is_run_exactly_once_to_acquire_coverage_0()
        print('PASS test_cov_cmd_is_run_exactly_once_to_acquire_coverage_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_cov_cmd_is_run_exactly_once_to_acquire_coverage_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_reuse_coverage_reads_coverage_lcov_without_regenerating_0()
        print('PASS test_reuse_coverage_reads_coverage_lcov_without_regenerating_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_reuse_coverage_reads_coverage_lcov_without_regenerating_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_missing_or_unusable_coverage_source_exits_non_zero_and_pri_0()
        print('PASS test_a_missing_or_unusable_coverage_source_exits_non_zero_and_pri_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_missing_or_unusable_coverage_source_exits_non_zero_and_pri_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_missing_or_unusable_coverage_source_exits_non_zero_and_pri_1()
        print('PASS test_a_missing_or_unusable_coverage_source_exits_non_zero_and_pri_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_missing_or_unusable_coverage_source_exits_non_zero_and_pri_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_supplying_more_than_one_coverage_flag_is_a_usage_error_0()
        print('PASS test_supplying_more_than_one_coverage_flag_is_a_usage_error_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_supplying_more_than_one_coverage_flag_is_a_usage_error_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_supplying_more_than_one_coverage_flag_is_a_usage_error_1()
        print('PASS test_supplying_more_than_one_coverage_flag_is_a_usage_error_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_supplying_more_than_one_coverage_flag_is_a_usage_error_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_supplying_more_than_one_coverage_flag_is_a_usage_error_2()
        print('PASS test_supplying_more_than_one_coverage_flag_is_a_usage_error_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_supplying_more_than_one_coverage_flag_is_a_usage_error_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_scanning_with_coverage_leaves_the_source_byte_identical_and__0()
        print('PASS test_scanning_with_coverage_leaves_the_source_byte_identical_and__0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_scanning_with_coverage_leaves_the_source_byte_identical_and__0: {e}')
        traceback.print_exc()
        failed += 1
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)
