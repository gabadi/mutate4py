import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from acceptance.steps.cli_surface_qa_steps import run_step

# Scenario data baked in; APS_FEATURE_JSON overrides for gherkin mutation
_aps_override = os.environ.get('APS_FEATURE_JSON')
if _aps_override:
    with open(_aps_override) as _f:
        _ir = json.load(_f)
    _background = _ir.get('background', [])
    _scenarios = _ir.get('scenarios', [])
else:
    _background = [{'keyword': 'Given', 'text': 'a temp project directory with a real Python source file holding a mutation site'}]
    _scenarios = [{'name': 'a rejected invocation exits non-zero and leaves the source untouched', 'steps': [{'keyword': 'When', 'text': 'I invoke the mutate4py command described by "<invocation>"', 'parameters': ['invocation']}, {'keyword': 'Then', 'text': 'the command exits non-zero'}, {'keyword': 'And', 'text': 'the printed output names the offending flag or combination'}, {'keyword': 'And', 'text': 'the source file is byte-identical to before the run'}, {'keyword': 'And', 'text': 'no ".mutate4py.bak" file was created'}], 'examples': [{'invocation': '--mutation-warning 0'}, {'invocation': '--max-workers -1'}, {'invocation': '--timeout-factor 1.5'}, {'invocation': '--lines 7,x'}, {'invocation': '--scan --max-workers 4'}, {'invocation': '--scan --mutate-all'}, {'invocation': '--update-manifest --lines 7'}, {'invocation': '--since-last-run --mutate-all'}, {'invocation': '--lcov cov.info --reuse-coverage'}, {'invocation': '--bogus-flag'}, {'invocation': '(a path that does not exist)'}, {'invocation': '(no source file argument)'}, {'invocation': '--max-workers (with no value)'}]}, {'name': '--help prints the usage summary and wins over invalid companion args', 'steps': [{'keyword': 'When', 'text': 'I invoke "mutate4py --help --scan --mutate-all"'}, {'keyword': 'Then', 'text': 'the command exits zero'}, {'keyword': 'And', 'text': 'the printed output contains a usage summary'}, {'keyword': 'And', 'text': 'the printed output contains "--max-workers"'}], 'examples': []}, {'name': 'an accepted no-run mode is reached', 'steps': [{'keyword': 'When', 'text': 'I invoke the mutate4py command with the accepted "<mode>"', 'parameters': ['mode']}, {'keyword': 'Then', 'text': 'the command exits zero'}, {'keyword': 'And', 'text': 'the printed output contains the mode\'s lead marker "<marker>"', 'parameters': ['marker']}], 'examples': [{'mode': '--scan', 'marker': 'Mutation scan:'}, {'mode': '--update-manifest', 'marker': 'manifest'}]}, {'name': '--max-workers alongside a coverage flag is accepted and runs', 'steps': [{'keyword': 'Given', 'text': 'a minimal LCOV fixture covering the site and a fast fake test command'}, {'keyword': 'When', 'text': 'I invoke "mutate4py <file> --lcov cov.info --max-workers 4 --test-command <fake>"', 'parameters': ['file', 'fake']}, {'keyword': 'Then', 'text': 'the command exits zero'}, {'keyword': 'And', 'text': 'the printed output contains "Mutation run:"'}], 'examples': []}, {'name': '--max-workers and a selection flag are accepted together', 'steps': [{'keyword': 'Given', 'text': 'a minimal LCOV fixture covering the site and a fast fake test command'}, {'keyword': 'When', 'text': 'I invoke "mutate4py <file> --lcov cov.info --max-workers 4 --mutate-all --test-command <fake>"', 'parameters': ['file', 'fake']}, {'keyword': 'Then', 'text': 'the command exits zero'}], 'examples': []}]

def test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_0():
    """Scenario: a rejected invocation exits non-zero and leaves the source untouched — example 0"""
    _s = _scenarios[0]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_1():
    """Scenario: a rejected invocation exits non-zero and leaves the source untouched — example 1"""
    _s = _scenarios[0]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_2():
    """Scenario: a rejected invocation exits non-zero and leaves the source untouched — example 2"""
    _s = _scenarios[0]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_3():
    """Scenario: a rejected invocation exits non-zero and leaves the source untouched — example 3"""
    _s = _scenarios[0]
    _ex = _s['examples'][3] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_4():
    """Scenario: a rejected invocation exits non-zero and leaves the source untouched — example 4"""
    _s = _scenarios[0]
    _ex = _s['examples'][4] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_5():
    """Scenario: a rejected invocation exits non-zero and leaves the source untouched — example 5"""
    _s = _scenarios[0]
    _ex = _s['examples'][5] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_6():
    """Scenario: a rejected invocation exits non-zero and leaves the source untouched — example 6"""
    _s = _scenarios[0]
    _ex = _s['examples'][6] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_7():
    """Scenario: a rejected invocation exits non-zero and leaves the source untouched — example 7"""
    _s = _scenarios[0]
    _ex = _s['examples'][7] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_8():
    """Scenario: a rejected invocation exits non-zero and leaves the source untouched — example 8"""
    _s = _scenarios[0]
    _ex = _s['examples'][8] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_9():
    """Scenario: a rejected invocation exits non-zero and leaves the source untouched — example 9"""
    _s = _scenarios[0]
    _ex = _s['examples'][9] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_10():
    """Scenario: a rejected invocation exits non-zero and leaves the source untouched — example 10"""
    _s = _scenarios[0]
    _ex = _s['examples'][10] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_11():
    """Scenario: a rejected invocation exits non-zero and leaves the source untouched — example 11"""
    _s = _scenarios[0]
    _ex = _s['examples'][11] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_12():
    """Scenario: a rejected invocation exits non-zero and leaves the source untouched — example 12"""
    _s = _scenarios[0]
    _ex = _s['examples'][12] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_help_prints_the_usage_summary_and_wins_over_invalid_companio_0():
    """Scenario: --help prints the usage summary and wins over invalid companion args — example 0"""
    _s = _scenarios[1]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_an_accepted_no_run_mode_is_reached_0():
    """Scenario: an accepted no-run mode is reached — example 0"""
    _s = _scenarios[2]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_an_accepted_no_run_mode_is_reached_1():
    """Scenario: an accepted no-run mode is reached — example 1"""
    _s = _scenarios[2]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_max_workers_alongside_a_coverage_flag_is_accepted_and_runs_0():
    """Scenario: --max-workers alongside a coverage flag is accepted and runs — example 0"""
    _s = _scenarios[3]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_max_workers_and_a_selection_flag_are_accepted_together_0():
    """Scenario: --max-workers and a selection flag are accepted together — example 0"""
    _s = _scenarios[4]
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
        test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_0()
        print('PASS test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_1()
        print('PASS test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_2()
        print('PASS test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_3()
        print('PASS test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_3')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_3: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_4()
        print('PASS test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_4')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_4: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_5()
        print('PASS test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_5')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_5: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_6()
        print('PASS test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_6')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_6: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_7()
        print('PASS test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_7')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_7: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_8()
        print('PASS test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_8')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_8: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_9()
        print('PASS test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_9')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_9: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_10()
        print('PASS test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_10')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_10: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_11()
        print('PASS test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_11')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_11: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_12()
        print('PASS test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_12')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_rejected_invocation_exits_non_zero_and_leaves_the_source_u_12: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_help_prints_the_usage_summary_and_wins_over_invalid_companio_0()
        print('PASS test_help_prints_the_usage_summary_and_wins_over_invalid_companio_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_help_prints_the_usage_summary_and_wins_over_invalid_companio_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_an_accepted_no_run_mode_is_reached_0()
        print('PASS test_an_accepted_no_run_mode_is_reached_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_an_accepted_no_run_mode_is_reached_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_an_accepted_no_run_mode_is_reached_1()
        print('PASS test_an_accepted_no_run_mode_is_reached_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_an_accepted_no_run_mode_is_reached_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_max_workers_alongside_a_coverage_flag_is_accepted_and_runs_0()
        print('PASS test_max_workers_alongside_a_coverage_flag_is_accepted_and_runs_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_max_workers_alongside_a_coverage_flag_is_accepted_and_runs_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_max_workers_and_a_selection_flag_are_accepted_together_0()
        print('PASS test_max_workers_and_a_selection_flag_are_accepted_together_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_max_workers_and_a_selection_flag_are_accepted_together_0: {e}')
        traceback.print_exc()
        failed += 1
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)
