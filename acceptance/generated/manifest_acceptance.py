import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from acceptance.steps.manifest_steps import run_step

# Scenario data baked in; APS_FEATURE_JSON overrides for gherkin mutation
_aps_override = os.environ.get('APS_FEATURE_JSON')
if _aps_override:
    with open(_aps_override) as _f:
        _ir = json.load(_f)
    _background = _ir.get('background', [])
    _scenarios = _ir.get('scenarios', [])
else:
    _background = []
    _scenarios = [{'name': 'embedding a manifest appends the marked footer', 'steps': [{'keyword': 'Given', 'text': 'a Python source file with no embedded manifest'}, {'keyword': 'When', 'text': 'a manifest is embedded into the file'}, {'keyword': 'Then', 'text': 'the file contains the line "# mutate4py-manifest-begin"'}, {'keyword': 'And', 'text': 'the file contains the line "# mutate4py-manifest-end"'}, {'keyword': 'And', 'text': 'the manifest JSON line begins with "# "'}, {'keyword': 'And', 'text': 'the manifest body above the footer is the original source with trailing newlines trimmed'}], 'examples': []}, {'name': 'the embedded manifest records the required fields', 'steps': [{'keyword': 'Given', 'text': 'a Python source file defining "def foo"'}, {'keyword': 'When', 'text': 'a manifest is embedded into the file'}, {'keyword': 'And', 'text': 'the embedded manifest is extracted'}, {'keyword': 'Then', 'text': 'the manifest field "<field>" is present', 'parameters': ['field']}], 'examples': [{'field': 'version'}, {'field': 'tested_at'}, {'field': 'module_hash'}, {'field': 'functions'}]}, {'name': 'a function unit is recorded with its id, name, range, and hash', 'steps': [{'keyword': 'Given', 'text': 'a Python source file defining "<definition>"', 'parameters': ['definition']}, {'keyword': 'When', 'text': 'a manifest is embedded into the file'}, {'keyword': 'And', 'text': 'the embedded manifest is extracted'}, {'keyword': 'Then', 'text': 'the first function record has id "<id>" and name "<name>"', 'parameters': ['id', 'name']}, {'keyword': 'And', 'text': 'the first function record has a "line", an "end_line", and a "hash"'}], 'examples': [{'definition': 'def foo', 'id': 'func/foo', 'name': 'foo'}, {'definition': 'async def foo', 'id': 'func/foo', 'name': 'foo'}, {'definition': 'class C with method m', 'id': 'func/C.m', 'name': 'm'}]}, {'name': 'a decorated function records the def line, not the decorator line', 'steps': [{'keyword': 'Given', 'text': 'a Python source file with a decorator above "def foo" on line <def_line>', 'parameters': ['def_line']}, {'keyword': 'When', 'text': 'a manifest is embedded into the file'}, {'keyword': 'And', 'text': 'the embedded manifest is extracted'}, {'keyword': 'Then', 'text': 'the first function record "line" is <def_line>', 'parameters': ['def_line']}], 'examples': [{'def_line': '2'}]}, {'name': 'a module with only module-level code records no functions', 'steps': [{'keyword': 'Given', 'text': 'a Python source file with module-level code and no function definitions'}, {'keyword': 'When', 'text': 'a manifest is embedded into the file'}, {'keyword': 'And', 'text': 'the embedded manifest is extracted'}, {'keyword': 'Then', 'text': 'the manifest "functions" list is empty'}, {'keyword': 'And', 'text': 'the manifest "module_hash" is a non-empty hash'}], 'examples': []}, {'name': 'extracting a manifest returns the object that was embedded', 'steps': [{'keyword': 'Given', 'text': 'a Python source file with no embedded manifest'}, {'keyword': 'When', 'text': 'a manifest is embedded into the file'}, {'keyword': 'And', 'text': 'the embedded manifest is extracted'}, {'keyword': 'Then', 'text': 'the extracted manifest equals the embedded manifest'}], 'examples': []}, {'name': 'extracting a file without a valid manifest yields none', 'steps': [{'keyword': 'Given', 'text': 'a Python source file whose footer is "<footer>"', 'parameters': ['footer']}, {'keyword': 'When', 'text': 'the file is extracted'}, {'keyword': 'Then', 'text': 'the extract result is "no manifest"'}], 'examples': [{'footer': '(no markers at all)'}, {'footer': '# mutate4py-manifest-begin only, no end marker'}, {'footer': 'both markers around text that is not valid JSON'}]}, {'name': 're-embedding replaces the existing footer', 'steps': [{'keyword': 'Given', 'text': 'a Python source file with an embedded manifest'}, {'keyword': 'When', 'text': 'a manifest is embedded into the file'}, {'keyword': 'Then', 'text': 'the file contains exactly one "# mutate4py-manifest-begin" line'}, {'keyword': 'And', 'text': 'the manifest body above the footer is byte-identical to the once-embedded body'}], 'examples': []}, {'name': 'a "<edit>" edit leaves the function unchanged in the diff', 'steps': [{'keyword': 'Given', 'text': 'a previous manifest built from a function'}, {'keyword': 'And', 'text': 'the function is changed by "<edit>"', 'parameters': ['edit']}, {'keyword': 'When', 'text': 'the previous manifest is diffed against the current manifest'}, {'keyword': 'Then', 'text': 'the changed function ids are "<changed>"', 'parameters': ['changed']}], 'examples': [{'edit': 'reformatting whitespace', 'changed': ''}, {'edit': 'editing a comment', 'changed': ''}, {'edit': 'renaming the function', 'changed': 'func/foo'}, {'edit': 'changing a numeric literal', 'changed': 'func/foo'}, {'edit': 'changing an operator', 'changed': 'func/foo'}]}, {'name': 'diffing previous against current reports the changed id set', 'steps': [{'keyword': 'Given', 'text': 'a previous manifest with functions "<previous>"', 'parameters': ['previous']}, {'keyword': 'And', 'text': 'a current manifest with functions "<current>"', 'parameters': ['current']}, {'keyword': 'When', 'text': 'the previous manifest is diffed against the current manifest'}, {'keyword': 'Then', 'text': 'the changed function ids are "<changed>"', 'parameters': ['changed']}], 'examples': [{'previous': 'none', 'current': 'func/a, func/b', 'changed': 'func/a, func/b'}, {'previous': 'func/a:h1', 'current': 'func/a:h1', 'changed': ''}, {'previous': 'func/a:h1', 'current': 'func/a:h2', 'changed': 'func/a'}, {'previous': 'func/a:h1', 'current': 'func/a:h1, func/b:h3', 'changed': 'func/b'}, {'previous': 'func/a:h1, func/b:h2', 'current': 'func/a:h1', 'changed': ''}]}, {'name': 'updating the manifest on a file without one writes and reports it', 'steps': [{'keyword': 'Given', 'text': 'a Python source file with no embedded manifest'}, {'keyword': 'When', 'text': 'the command "mutate4py <file> --update-manifest" is run', 'parameters': ['file']}, {'keyword': 'Then', 'text': 'the output line "Updated manifest: <file>" is printed', 'parameters': ['file']}, {'keyword': 'And', 'text': 'the file then contains an embedded manifest'}, {'keyword': 'And', 'text': 'no test command is run'}], 'examples': []}, {'name': 're-running --update-manifest reflects whether anything changed', 'steps': [{'keyword': 'Given', 'text': 'a Python source file with an embedded manifest current as of its content'}, {'keyword': 'And', 'text': 'the file is then changed by "<edit>"', 'parameters': ['edit']}, {'keyword': 'When', 'text': 'the command "mutate4py <file> --update-manifest" is run', 'parameters': ['file']}, {'keyword': 'Then', 'text': 'the output line "<output>" is printed', 'parameters': ['output']}, {'keyword': 'And', 'text': 'the file footer is "<footer_state>"', 'parameters': ['footer_state']}], 'examples': [{'edit': 'nothing', 'output': 'Manifest unchanged: <file>', 'footer_state': 'byte-identical'}, {'edit': 'reformatting whitespace', 'output': 'Manifest unchanged: <file>', 'footer_state': 'byte-identical'}, {'edit': 'changing an operator', 'output': 'Updated manifest: <file>', 'footer_state': 'rewritten'}]}, {'name': 'updating the manifest of a missing file is a usage error', 'steps': [{'keyword': 'Given', 'text': 'the path "<missing>" does not exist', 'parameters': ['missing']}, {'keyword': 'When', 'text': 'the command "mutate4py <missing> --update-manifest" is run', 'parameters': ['missing']}, {'keyword': 'Then', 'text': 'the command exits with a usage error'}, {'keyword': 'And', 'text': 'no manifest is written'}], 'examples': []}]

def test_embedding_a_manifest_appends_the_marked_footer_0():
    """Scenario: embedding a manifest appends the marked footer — example 0"""
    _s = _scenarios[0]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_embedded_manifest_records_the_required_fields_0():
    """Scenario: the embedded manifest records the required fields — example 0"""
    _s = _scenarios[1]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_embedded_manifest_records_the_required_fields_1():
    """Scenario: the embedded manifest records the required fields — example 1"""
    _s = _scenarios[1]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_embedded_manifest_records_the_required_fields_2():
    """Scenario: the embedded manifest records the required fields — example 2"""
    _s = _scenarios[1]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_embedded_manifest_records_the_required_fields_3():
    """Scenario: the embedded manifest records the required fields — example 3"""
    _s = _scenarios[1]
    _ex = _s['examples'][3] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_function_unit_is_recorded_with_its_id_name_range_and_hash_0():
    """Scenario: a function unit is recorded with its id, name, range, and hash — example 0"""
    _s = _scenarios[2]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_function_unit_is_recorded_with_its_id_name_range_and_hash_1():
    """Scenario: a function unit is recorded with its id, name, range, and hash — example 1"""
    _s = _scenarios[2]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_function_unit_is_recorded_with_its_id_name_range_and_hash_2():
    """Scenario: a function unit is recorded with its id, name, range, and hash — example 2"""
    _s = _scenarios[2]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_decorated_function_records_the_def_line_not_the_decorator__0():
    """Scenario: a decorated function records the def line, not the decorator line — example 0"""
    _s = _scenarios[3]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_module_with_only_module_level_code_records_no_functions_0():
    """Scenario: a module with only module-level code records no functions — example 0"""
    _s = _scenarios[4]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_extracting_a_manifest_returns_the_object_that_was_embedded_0():
    """Scenario: extracting a manifest returns the object that was embedded — example 0"""
    _s = _scenarios[5]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_extracting_a_file_without_a_valid_manifest_yields_none_0():
    """Scenario: extracting a file without a valid manifest yields none — example 0"""
    _s = _scenarios[6]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_extracting_a_file_without_a_valid_manifest_yields_none_1():
    """Scenario: extracting a file without a valid manifest yields none — example 1"""
    _s = _scenarios[6]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_extracting_a_file_without_a_valid_manifest_yields_none_2():
    """Scenario: extracting a file without a valid manifest yields none — example 2"""
    _s = _scenarios[6]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_re_embedding_replaces_the_existing_footer_0():
    """Scenario: re-embedding replaces the existing footer — example 0"""
    _s = _scenarios[7]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_0():
    """Scenario: a "<edit>" edit leaves the function unchanged in the diff — example 0"""
    _s = _scenarios[8]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_1():
    """Scenario: a "<edit>" edit leaves the function unchanged in the diff — example 1"""
    _s = _scenarios[8]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_2():
    """Scenario: a "<edit>" edit leaves the function unchanged in the diff — example 2"""
    _s = _scenarios[8]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_3():
    """Scenario: a "<edit>" edit leaves the function unchanged in the diff — example 3"""
    _s = _scenarios[8]
    _ex = _s['examples'][3] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_4():
    """Scenario: a "<edit>" edit leaves the function unchanged in the diff — example 4"""
    _s = _scenarios[8]
    _ex = _s['examples'][4] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_diffing_previous_against_current_reports_the_changed_id_set_0():
    """Scenario: diffing previous against current reports the changed id set — example 0"""
    _s = _scenarios[9]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_diffing_previous_against_current_reports_the_changed_id_set_1():
    """Scenario: diffing previous against current reports the changed id set — example 1"""
    _s = _scenarios[9]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_diffing_previous_against_current_reports_the_changed_id_set_2():
    """Scenario: diffing previous against current reports the changed id set — example 2"""
    _s = _scenarios[9]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_diffing_previous_against_current_reports_the_changed_id_set_3():
    """Scenario: diffing previous against current reports the changed id set — example 3"""
    _s = _scenarios[9]
    _ex = _s['examples'][3] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_diffing_previous_against_current_reports_the_changed_id_set_4():
    """Scenario: diffing previous against current reports the changed id set — example 4"""
    _s = _scenarios[9]
    _ex = _s['examples'][4] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_updating_the_manifest_on_a_file_without_one_writes_and_repor_0():
    """Scenario: updating the manifest on a file without one writes and reports it — example 0"""
    _s = _scenarios[10]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_re_running_update_manifest_reflects_whether_anything_changed_0():
    """Scenario: re-running --update-manifest reflects whether anything changed — example 0"""
    _s = _scenarios[11]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_re_running_update_manifest_reflects_whether_anything_changed_1():
    """Scenario: re-running --update-manifest reflects whether anything changed — example 1"""
    _s = _scenarios[11]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_re_running_update_manifest_reflects_whether_anything_changed_2():
    """Scenario: re-running --update-manifest reflects whether anything changed — example 2"""
    _s = _scenarios[11]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_updating_the_manifest_of_a_missing_file_is_a_usage_error_0():
    """Scenario: updating the manifest of a missing file is a usage error — example 0"""
    _s = _scenarios[12]
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
        test_embedding_a_manifest_appends_the_marked_footer_0()
        print('PASS test_embedding_a_manifest_appends_the_marked_footer_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_embedding_a_manifest_appends_the_marked_footer_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_embedded_manifest_records_the_required_fields_0()
        print('PASS test_the_embedded_manifest_records_the_required_fields_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_embedded_manifest_records_the_required_fields_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_embedded_manifest_records_the_required_fields_1()
        print('PASS test_the_embedded_manifest_records_the_required_fields_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_embedded_manifest_records_the_required_fields_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_embedded_manifest_records_the_required_fields_2()
        print('PASS test_the_embedded_manifest_records_the_required_fields_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_embedded_manifest_records_the_required_fields_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_embedded_manifest_records_the_required_fields_3()
        print('PASS test_the_embedded_manifest_records_the_required_fields_3')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_embedded_manifest_records_the_required_fields_3: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_function_unit_is_recorded_with_its_id_name_range_and_hash_0()
        print('PASS test_a_function_unit_is_recorded_with_its_id_name_range_and_hash_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_function_unit_is_recorded_with_its_id_name_range_and_hash_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_function_unit_is_recorded_with_its_id_name_range_and_hash_1()
        print('PASS test_a_function_unit_is_recorded_with_its_id_name_range_and_hash_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_function_unit_is_recorded_with_its_id_name_range_and_hash_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_function_unit_is_recorded_with_its_id_name_range_and_hash_2()
        print('PASS test_a_function_unit_is_recorded_with_its_id_name_range_and_hash_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_function_unit_is_recorded_with_its_id_name_range_and_hash_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_decorated_function_records_the_def_line_not_the_decorator__0()
        print('PASS test_a_decorated_function_records_the_def_line_not_the_decorator__0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_decorated_function_records_the_def_line_not_the_decorator__0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_module_with_only_module_level_code_records_no_functions_0()
        print('PASS test_a_module_with_only_module_level_code_records_no_functions_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_module_with_only_module_level_code_records_no_functions_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_extracting_a_manifest_returns_the_object_that_was_embedded_0()
        print('PASS test_extracting_a_manifest_returns_the_object_that_was_embedded_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_extracting_a_manifest_returns_the_object_that_was_embedded_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_extracting_a_file_without_a_valid_manifest_yields_none_0()
        print('PASS test_extracting_a_file_without_a_valid_manifest_yields_none_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_extracting_a_file_without_a_valid_manifest_yields_none_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_extracting_a_file_without_a_valid_manifest_yields_none_1()
        print('PASS test_extracting_a_file_without_a_valid_manifest_yields_none_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_extracting_a_file_without_a_valid_manifest_yields_none_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_extracting_a_file_without_a_valid_manifest_yields_none_2()
        print('PASS test_extracting_a_file_without_a_valid_manifest_yields_none_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_extracting_a_file_without_a_valid_manifest_yields_none_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_re_embedding_replaces_the_existing_footer_0()
        print('PASS test_re_embedding_replaces_the_existing_footer_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_re_embedding_replaces_the_existing_footer_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_0()
        print('PASS test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_1()
        print('PASS test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_2()
        print('PASS test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_3()
        print('PASS test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_3')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_3: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_4()
        print('PASS test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_4')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_edit_edit_leaves_the_function_unchanged_in_the_diff_4: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_diffing_previous_against_current_reports_the_changed_id_set_0()
        print('PASS test_diffing_previous_against_current_reports_the_changed_id_set_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_diffing_previous_against_current_reports_the_changed_id_set_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_diffing_previous_against_current_reports_the_changed_id_set_1()
        print('PASS test_diffing_previous_against_current_reports_the_changed_id_set_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_diffing_previous_against_current_reports_the_changed_id_set_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_diffing_previous_against_current_reports_the_changed_id_set_2()
        print('PASS test_diffing_previous_against_current_reports_the_changed_id_set_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_diffing_previous_against_current_reports_the_changed_id_set_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_diffing_previous_against_current_reports_the_changed_id_set_3()
        print('PASS test_diffing_previous_against_current_reports_the_changed_id_set_3')
        passed += 1
    except Exception as e:
        print(f'FAIL test_diffing_previous_against_current_reports_the_changed_id_set_3: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_diffing_previous_against_current_reports_the_changed_id_set_4()
        print('PASS test_diffing_previous_against_current_reports_the_changed_id_set_4')
        passed += 1
    except Exception as e:
        print(f'FAIL test_diffing_previous_against_current_reports_the_changed_id_set_4: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_updating_the_manifest_on_a_file_without_one_writes_and_repor_0()
        print('PASS test_updating_the_manifest_on_a_file_without_one_writes_and_repor_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_updating_the_manifest_on_a_file_without_one_writes_and_repor_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_re_running_update_manifest_reflects_whether_anything_changed_0()
        print('PASS test_re_running_update_manifest_reflects_whether_anything_changed_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_re_running_update_manifest_reflects_whether_anything_changed_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_re_running_update_manifest_reflects_whether_anything_changed_1()
        print('PASS test_re_running_update_manifest_reflects_whether_anything_changed_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_re_running_update_manifest_reflects_whether_anything_changed_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_re_running_update_manifest_reflects_whether_anything_changed_2()
        print('PASS test_re_running_update_manifest_reflects_whether_anything_changed_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_re_running_update_manifest_reflects_whether_anything_changed_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_updating_the_manifest_of_a_missing_file_is_a_usage_error_0()
        print('PASS test_updating_the_manifest_of_a_missing_file_is_a_usage_error_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_updating_the_manifest_of_a_missing_file_is_a_usage_error_0: {e}')
        traceback.print_exc()
        failed += 1
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)
