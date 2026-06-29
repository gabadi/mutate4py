import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from acceptance.steps.site_discovery_steps import run_step

# Scenario data baked in; APS_FEATURE_JSON overrides for gherkin mutation
_aps_override = os.environ.get('APS_FEATURE_JSON')
if _aps_override:
    with open(_aps_override) as _f:
        _ir = json.load(_f)
    _background = _ir.get('background', [])
    _scenarios = _ir.get('scenarios', [])
else:
    _background = []
    _scenarios = [{'name': 'a catalogued construct yields one mutation site', 'steps': [{'keyword': 'Given', 'text': 'a Python file whose only mutable construct is "<construct>"', 'parameters': ['construct']}, {'keyword': 'When', 'text': 'the file is scanned'}, {'keyword': 'Then', 'text': 'the total mutation sites is <count>', 'parameters': ['count']}], 'examples': [{'construct': 'a + b', 'count': '1'}, {'construct': 'a - b', 'count': '1'}, {'construct': 'a * b', 'count': '1'}, {'construct': 'a > b', 'count': '1'}, {'construct': 'a >= b', 'count': '1'}, {'construct': 'a < b', 'count': '1'}, {'construct': 'a <= b', 'count': '1'}, {'construct': 'a == b', 'count': '1'}, {'construct': 'a != b', 'count': '1'}, {'construct': 'a is b', 'count': '1'}, {'construct': 'a is not b', 'count': '1'}, {'construct': 'a in b', 'count': '1'}, {'construct': 'a not in b', 'count': '1'}, {'construct': 'a and b', 'count': '1'}, {'construct': 'a or b', 'count': '1'}, {'construct': 'True', 'count': '1'}, {'construct': 'False', 'count': '1'}, {'construct': '0', 'count': '1'}, {'construct': '1', 'count': '1'}]}, {'name': 'an excluded construct yields no mutation site', 'steps': [{'keyword': 'Given', 'text': 'a Python file whose only candidate construct is "<construct>"', 'parameters': ['construct']}, {'keyword': 'When', 'text': 'the file is scanned'}, {'keyword': 'Then', 'text': 'the total mutation sites is 0'}], 'examples': [{'construct': 'a += b'}, {'construct': 'a -= b'}, {'construct': 'a / b'}, {'construct': '-a'}, {'construct': '2'}]}, {'name': 'a site inside a function is attributed to that unit', 'steps': [{'keyword': 'Given', 'text': 'a Python file defining "<definition>" containing one mutable site', 'parameters': ['definition']}, {'keyword': 'When', 'text': 'the file is scanned'}, {'keyword': 'Then', 'text': 'the site\'s function id is "<function_id>"', 'parameters': ['function_id']}], 'examples': [{'definition': 'def foo', 'function_id': 'func/foo'}, {'definition': 'async def foo', 'function_id': 'func/foo'}, {'definition': 'class C with method m', 'function_id': 'func/C.m'}, {'definition': 'module-level code (no def)', 'function_id': ''}, {'definition': 'def outer with a nested def', 'function_id': 'func/outer'}, {'definition': 'def outer with a lambda', 'function_id': 'func/outer'}]}, {'name': 'scanning a file prints the count block with no manifest', 'steps': [{'keyword': 'Given', 'text': 'a Python file containing <total> mutation sites and no embedded manifest', 'parameters': ['total']}, {'keyword': 'When', 'text': 'the command "mutate4py <file> --scan" is run', 'parameters': ['file']}, {'keyword': 'Then', 'text': 'the output line "Total mutation sites: <total>" is printed', 'parameters': ['total']}, {'keyword': 'And', 'text': 'the output line "Changed mutation sites: <total>" is printed', 'parameters': ['total']}, {'keyword': 'And', 'text': 'the output line "Manifest exists: false" is printed'}, {'keyword': 'And', 'text': 'no test command is run'}, {'keyword': 'And', 'text': 'the file is left unchanged'}], 'examples': [{'total': '0'}, {'total': '1'}, {'total': '7'}]}, {'name': 'the warning line is gated by the threshold', 'steps': [{'keyword': 'Given', 'text': 'a Python file containing <total> mutation sites', 'parameters': ['total']}, {'keyword': 'And', 'text': 'the mutation warning threshold is <threshold>', 'parameters': ['threshold']}, {'keyword': 'When', 'text': 'the file is scanned'}, {'keyword': 'Then', 'text': 'the warning line is "<warning>"', 'parameters': ['warning']}], 'examples': [{'total': '50', 'threshold': '50', 'warning': ''}, {'total': '51', 'threshold': '50', 'warning': 'Warning: 51 mutation sites exceeds threshold 50.'}, {'total': '3', 'threshold': '2', 'warning': 'Warning: 3 mutation sites exceeds threshold 2.'}]}, {'name': 'scanning a missing file is a usage error', 'steps': [{'keyword': 'Given', 'text': 'the path "<missing>" does not exist', 'parameters': ['missing']}, {'keyword': 'When', 'text': 'the command "mutate4py <missing> --scan" is run', 'parameters': ['missing']}, {'keyword': 'Then', 'text': 'the command exits with a usage error'}, {'keyword': 'And', 'text': 'no mutation scan block is printed'}], 'examples': []}]

def test_a_catalogued_construct_yields_one_mutation_site_0():
    """Scenario: a catalogued construct yields one mutation site — example 0"""
    _s = _scenarios[0]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_1():
    """Scenario: a catalogued construct yields one mutation site — example 1"""
    _s = _scenarios[0]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_2():
    """Scenario: a catalogued construct yields one mutation site — example 2"""
    _s = _scenarios[0]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_3():
    """Scenario: a catalogued construct yields one mutation site — example 3"""
    _s = _scenarios[0]
    _ex = _s['examples'][3] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_4():
    """Scenario: a catalogued construct yields one mutation site — example 4"""
    _s = _scenarios[0]
    _ex = _s['examples'][4] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_5():
    """Scenario: a catalogued construct yields one mutation site — example 5"""
    _s = _scenarios[0]
    _ex = _s['examples'][5] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_6():
    """Scenario: a catalogued construct yields one mutation site — example 6"""
    _s = _scenarios[0]
    _ex = _s['examples'][6] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_7():
    """Scenario: a catalogued construct yields one mutation site — example 7"""
    _s = _scenarios[0]
    _ex = _s['examples'][7] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_8():
    """Scenario: a catalogued construct yields one mutation site — example 8"""
    _s = _scenarios[0]
    _ex = _s['examples'][8] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_9():
    """Scenario: a catalogued construct yields one mutation site — example 9"""
    _s = _scenarios[0]
    _ex = _s['examples'][9] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_10():
    """Scenario: a catalogued construct yields one mutation site — example 10"""
    _s = _scenarios[0]
    _ex = _s['examples'][10] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_11():
    """Scenario: a catalogued construct yields one mutation site — example 11"""
    _s = _scenarios[0]
    _ex = _s['examples'][11] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_12():
    """Scenario: a catalogued construct yields one mutation site — example 12"""
    _s = _scenarios[0]
    _ex = _s['examples'][12] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_13():
    """Scenario: a catalogued construct yields one mutation site — example 13"""
    _s = _scenarios[0]
    _ex = _s['examples'][13] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_14():
    """Scenario: a catalogued construct yields one mutation site — example 14"""
    _s = _scenarios[0]
    _ex = _s['examples'][14] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_15():
    """Scenario: a catalogued construct yields one mutation site — example 15"""
    _s = _scenarios[0]
    _ex = _s['examples'][15] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_16():
    """Scenario: a catalogued construct yields one mutation site — example 16"""
    _s = _scenarios[0]
    _ex = _s['examples'][16] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_17():
    """Scenario: a catalogued construct yields one mutation site — example 17"""
    _s = _scenarios[0]
    _ex = _s['examples'][17] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_catalogued_construct_yields_one_mutation_site_18():
    """Scenario: a catalogued construct yields one mutation site — example 18"""
    _s = _scenarios[0]
    _ex = _s['examples'][18] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_an_excluded_construct_yields_no_mutation_site_0():
    """Scenario: an excluded construct yields no mutation site — example 0"""
    _s = _scenarios[1]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_an_excluded_construct_yields_no_mutation_site_1():
    """Scenario: an excluded construct yields no mutation site — example 1"""
    _s = _scenarios[1]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_an_excluded_construct_yields_no_mutation_site_2():
    """Scenario: an excluded construct yields no mutation site — example 2"""
    _s = _scenarios[1]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_an_excluded_construct_yields_no_mutation_site_3():
    """Scenario: an excluded construct yields no mutation site — example 3"""
    _s = _scenarios[1]
    _ex = _s['examples'][3] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_an_excluded_construct_yields_no_mutation_site_4():
    """Scenario: an excluded construct yields no mutation site — example 4"""
    _s = _scenarios[1]
    _ex = _s['examples'][4] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_site_inside_a_function_is_attributed_to_that_unit_0():
    """Scenario: a site inside a function is attributed to that unit — example 0"""
    _s = _scenarios[2]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_site_inside_a_function_is_attributed_to_that_unit_1():
    """Scenario: a site inside a function is attributed to that unit — example 1"""
    _s = _scenarios[2]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_site_inside_a_function_is_attributed_to_that_unit_2():
    """Scenario: a site inside a function is attributed to that unit — example 2"""
    _s = _scenarios[2]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_site_inside_a_function_is_attributed_to_that_unit_3():
    """Scenario: a site inside a function is attributed to that unit — example 3"""
    _s = _scenarios[2]
    _ex = _s['examples'][3] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_site_inside_a_function_is_attributed_to_that_unit_4():
    """Scenario: a site inside a function is attributed to that unit — example 4"""
    _s = _scenarios[2]
    _ex = _s['examples'][4] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_site_inside_a_function_is_attributed_to_that_unit_5():
    """Scenario: a site inside a function is attributed to that unit — example 5"""
    _s = _scenarios[2]
    _ex = _s['examples'][5] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_scanning_a_file_prints_the_count_block_with_no_manifest_0():
    """Scenario: scanning a file prints the count block with no manifest — example 0"""
    _s = _scenarios[3]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_scanning_a_file_prints_the_count_block_with_no_manifest_1():
    """Scenario: scanning a file prints the count block with no manifest — example 1"""
    _s = _scenarios[3]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_scanning_a_file_prints_the_count_block_with_no_manifest_2():
    """Scenario: scanning a file prints the count block with no manifest — example 2"""
    _s = _scenarios[3]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_warning_line_is_gated_by_the_threshold_0():
    """Scenario: the warning line is gated by the threshold — example 0"""
    _s = _scenarios[4]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_warning_line_is_gated_by_the_threshold_1():
    """Scenario: the warning line is gated by the threshold — example 1"""
    _s = _scenarios[4]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_warning_line_is_gated_by_the_threshold_2():
    """Scenario: the warning line is gated by the threshold — example 2"""
    _s = _scenarios[4]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_scanning_a_missing_file_is_a_usage_error_0():
    """Scenario: scanning a missing file is a usage error — example 0"""
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
        test_a_catalogued_construct_yields_one_mutation_site_0()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_1()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_2()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_3()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_3')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_3: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_4()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_4')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_4: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_5()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_5')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_5: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_6()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_6')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_6: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_7()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_7')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_7: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_8()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_8')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_8: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_9()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_9')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_9: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_10()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_10')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_10: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_11()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_11')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_11: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_12()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_12')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_12: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_13()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_13')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_13: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_14()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_14')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_14: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_15()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_15')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_15: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_16()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_16')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_16: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_17()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_17')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_17: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_catalogued_construct_yields_one_mutation_site_18()
        print('PASS test_a_catalogued_construct_yields_one_mutation_site_18')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_catalogued_construct_yields_one_mutation_site_18: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_an_excluded_construct_yields_no_mutation_site_0()
        print('PASS test_an_excluded_construct_yields_no_mutation_site_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_an_excluded_construct_yields_no_mutation_site_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_an_excluded_construct_yields_no_mutation_site_1()
        print('PASS test_an_excluded_construct_yields_no_mutation_site_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_an_excluded_construct_yields_no_mutation_site_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_an_excluded_construct_yields_no_mutation_site_2()
        print('PASS test_an_excluded_construct_yields_no_mutation_site_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_an_excluded_construct_yields_no_mutation_site_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_an_excluded_construct_yields_no_mutation_site_3()
        print('PASS test_an_excluded_construct_yields_no_mutation_site_3')
        passed += 1
    except Exception as e:
        print(f'FAIL test_an_excluded_construct_yields_no_mutation_site_3: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_an_excluded_construct_yields_no_mutation_site_4()
        print('PASS test_an_excluded_construct_yields_no_mutation_site_4')
        passed += 1
    except Exception as e:
        print(f'FAIL test_an_excluded_construct_yields_no_mutation_site_4: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_site_inside_a_function_is_attributed_to_that_unit_0()
        print('PASS test_a_site_inside_a_function_is_attributed_to_that_unit_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_site_inside_a_function_is_attributed_to_that_unit_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_site_inside_a_function_is_attributed_to_that_unit_1()
        print('PASS test_a_site_inside_a_function_is_attributed_to_that_unit_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_site_inside_a_function_is_attributed_to_that_unit_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_site_inside_a_function_is_attributed_to_that_unit_2()
        print('PASS test_a_site_inside_a_function_is_attributed_to_that_unit_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_site_inside_a_function_is_attributed_to_that_unit_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_site_inside_a_function_is_attributed_to_that_unit_3()
        print('PASS test_a_site_inside_a_function_is_attributed_to_that_unit_3')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_site_inside_a_function_is_attributed_to_that_unit_3: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_site_inside_a_function_is_attributed_to_that_unit_4()
        print('PASS test_a_site_inside_a_function_is_attributed_to_that_unit_4')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_site_inside_a_function_is_attributed_to_that_unit_4: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_site_inside_a_function_is_attributed_to_that_unit_5()
        print('PASS test_a_site_inside_a_function_is_attributed_to_that_unit_5')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_site_inside_a_function_is_attributed_to_that_unit_5: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_scanning_a_file_prints_the_count_block_with_no_manifest_0()
        print('PASS test_scanning_a_file_prints_the_count_block_with_no_manifest_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_scanning_a_file_prints_the_count_block_with_no_manifest_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_scanning_a_file_prints_the_count_block_with_no_manifest_1()
        print('PASS test_scanning_a_file_prints_the_count_block_with_no_manifest_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_scanning_a_file_prints_the_count_block_with_no_manifest_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_scanning_a_file_prints_the_count_block_with_no_manifest_2()
        print('PASS test_scanning_a_file_prints_the_count_block_with_no_manifest_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_scanning_a_file_prints_the_count_block_with_no_manifest_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_warning_line_is_gated_by_the_threshold_0()
        print('PASS test_the_warning_line_is_gated_by_the_threshold_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_warning_line_is_gated_by_the_threshold_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_warning_line_is_gated_by_the_threshold_1()
        print('PASS test_the_warning_line_is_gated_by_the_threshold_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_warning_line_is_gated_by_the_threshold_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_warning_line_is_gated_by_the_threshold_2()
        print('PASS test_the_warning_line_is_gated_by_the_threshold_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_warning_line_is_gated_by_the_threshold_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_scanning_a_missing_file_is_a_usage_error_0()
        print('PASS test_scanning_a_missing_file_is_a_usage_error_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_scanning_a_missing_file_is_a_usage_error_0: {e}')
        traceback.print_exc()
        failed += 1
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)
