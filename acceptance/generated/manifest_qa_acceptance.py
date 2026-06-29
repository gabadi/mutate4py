import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from acceptance.steps.manifest_qa_steps import run_step

# Scenario data baked in; APS_FEATURE_JSON overrides for gherkin mutation
_aps_override = os.environ.get('APS_FEATURE_JSON')
if _aps_override:
    with open(_aps_override) as _f:
        _ir = json.load(_f)
    _background = _ir.get('background', [])
    _scenarios = _ir.get('scenarios', [])
else:
    _background = [{'keyword': 'Given', 'text': 'the mutate4py command-line tool is installed'}, {'keyword': 'And', 'text': 'a writable copy of a committed Python fixture'}]
    _scenarios = [{'name': 'updating a fixture without a manifest writes the footer', 'steps': [{'keyword': 'Given', 'text': 'a fixture copy "plain.py" with no embedded manifest'}, {'keyword': 'When', 'text': 'the command "mutate4py plain.py --update-manifest" is run'}, {'keyword': 'Then', 'text': 'the command exits successfully'}, {'keyword': 'And', 'text': 'the output line "Updated manifest: plain.py" is printed'}, {'keyword': 'And', 'text': 'the file "plain.py" then contains a "# mutate4py-manifest-begin" line'}, {'keyword': 'And', 'text': 'the file "plain.py" then contains a "# mutate4py-manifest-end" line'}], 'examples': []}, {'name': 're-running update on an unchanged file reports it unchanged', 'steps': [{'keyword': 'Given', 'text': 'a fixture copy "plain.py" that already has a current embedded manifest'}, {'keyword': 'And', 'text': 'a recorded copy of its bytes'}, {'keyword': 'When', 'text': 'the command "mutate4py plain.py --update-manifest" is run'}, {'keyword': 'Then', 'text': 'the output line "Manifest unchanged: plain.py" is printed'}, {'keyword': 'And', 'text': 'the file "plain.py" on disk matches the recorded bytes exactly'}], 'examples': []}, {'name': 'updating after an operator change rewrites the footer', 'steps': [{'keyword': 'Given', 'text': 'a fixture copy "plain.py" with a current embedded manifest'}, {'keyword': 'And', 'text': 'the fixture copy is edited to change an operator'}, {'keyword': 'When', 'text': 'the command "mutate4py plain.py --update-manifest" is run'}, {'keyword': 'Then', 'text': 'the output line "Updated manifest: plain.py" is printed'}, {'keyword': 'And', 'text': 'the file "plain.py" still contains exactly one "# mutate4py-manifest-begin" line'}], 'examples': []}, {'name': 'updating after a whitespace-only edit reports unchanged', 'steps': [{'keyword': 'Given', 'text': 'a fixture copy "plain.py" with a current embedded manifest'}, {'keyword': 'And', 'text': 'the fixture copy is edited by reformatting whitespace only'}, {'keyword': 'When', 'text': 'the command "mutate4py plain.py --update-manifest" is run'}, {'keyword': 'Then', 'text': 'the output line "Manifest unchanged: plain.py" is printed'}], 'examples': []}, {'name': 'updating a path that does not exist fails as a usage error', 'steps': [{'keyword': 'Given', 'text': 'no file exists at "does_not_exist.py"'}, {'keyword': 'When', 'text': 'the command "mutate4py does_not_exist.py --update-manifest" is run'}, {'keyword': 'Then', 'text': 'the command exits with a non-zero status'}, {'keyword': 'And', 'text': 'no "Updated manifest:" line is printed'}, {'keyword': 'And', 'text': 'no file is created at "does_not_exist.py"'}], 'examples': []}, {'name': 'updating a file that already has a manifest keeps a single footer', 'steps': [{'keyword': 'Given', 'text': 'a fixture copy "stale.py" with an embedded manifest that is out of date'}, {'keyword': 'When', 'text': 'the command "mutate4py stale.py --update-manifest" is run'}, {'keyword': 'Then', 'text': 'the output line "Updated manifest: stale.py" is printed'}, {'keyword': 'And', 'text': 'the file "stale.py" contains exactly one "# mutate4py-manifest-begin" line'}, {'keyword': 'And', 'text': 'the file "stale.py" contains exactly one "# mutate4py-manifest-end" line'}], 'examples': []}]

def test_updating_a_fixture_without_a_manifest_writes_the_footer_0():
    """Scenario: updating a fixture without a manifest writes the footer — example 0"""
    _s = _scenarios[0]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_re_running_update_on_an_unchanged_file_reports_it_unchanged_0():
    """Scenario: re-running update on an unchanged file reports it unchanged — example 0"""
    _s = _scenarios[1]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_updating_after_an_operator_change_rewrites_the_footer_0():
    """Scenario: updating after an operator change rewrites the footer — example 0"""
    _s = _scenarios[2]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_updating_after_a_whitespace_only_edit_reports_unchanged_0():
    """Scenario: updating after a whitespace-only edit reports unchanged — example 0"""
    _s = _scenarios[3]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_updating_a_path_that_does_not_exist_fails_as_a_usage_error_0():
    """Scenario: updating a path that does not exist fails as a usage error — example 0"""
    _s = _scenarios[4]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_updating_a_file_that_already_has_a_manifest_keeps_a_single_f_0():
    """Scenario: updating a file that already has a manifest keeps a single footer — example 0"""
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
        test_updating_a_fixture_without_a_manifest_writes_the_footer_0()
        print('PASS test_updating_a_fixture_without_a_manifest_writes_the_footer_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_updating_a_fixture_without_a_manifest_writes_the_footer_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_re_running_update_on_an_unchanged_file_reports_it_unchanged_0()
        print('PASS test_re_running_update_on_an_unchanged_file_reports_it_unchanged_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_re_running_update_on_an_unchanged_file_reports_it_unchanged_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_updating_after_an_operator_change_rewrites_the_footer_0()
        print('PASS test_updating_after_an_operator_change_rewrites_the_footer_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_updating_after_an_operator_change_rewrites_the_footer_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_updating_after_a_whitespace_only_edit_reports_unchanged_0()
        print('PASS test_updating_after_a_whitespace_only_edit_reports_unchanged_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_updating_after_a_whitespace_only_edit_reports_unchanged_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_updating_a_path_that_does_not_exist_fails_as_a_usage_error_0()
        print('PASS test_updating_a_path_that_does_not_exist_fails_as_a_usage_error_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_updating_a_path_that_does_not_exist_fails_as_a_usage_error_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_updating_a_file_that_already_has_a_manifest_keeps_a_single_f_0()
        print('PASS test_updating_a_file_that_already_has_a_manifest_keeps_a_single_f_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_updating_a_file_that_already_has_a_manifest_keeps_a_single_f_0: {e}')
        traceback.print_exc()
        failed += 1
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)
