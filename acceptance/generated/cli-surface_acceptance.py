import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from acceptance.steps.cli_surface_steps import run_step

# Scenario data baked in; APS_FEATURE_JSON overrides for gherkin mutation
_aps_override = os.environ.get('APS_FEATURE_JSON')
if _aps_override:
    with open(_aps_override) as _f:
        _ir = json.load(_f)
    _background = _ir.get('background', [])
    _scenarios = _ir.get('scenarios', [])
else:
    _background = [{'keyword': 'Given', 'text': 'an existing Python source file with discovered mutation sites'}]
    _scenarios = [{'name': 'the full flag matrix parses and applies its default', 'steps': [{'keyword': 'When', 'text': 'I run mutate4py with the flag "<flag>"', 'parameters': ['flag']}, {'keyword': 'Then', 'text': 'the option "<option>" is set to "<value>"', 'parameters': ['option', 'value']}, {'keyword': 'And', 'text': 'the invocation is accepted'}], 'examples': [{'flag': '--mutation-warning 25', 'option': 'mutation-warning', 'value': '25'}, {'flag': '--timeout-factor 4', 'option': 'timeout-factor', 'value': '4'}, {'flag': '--test-command "tox"', 'option': 'test-command', 'value': 'tox'}, {'flag': '--max-workers 4', 'option': 'max-workers', 'value': '4'}, {'flag': '(none)', 'option': 'mutation-warning', 'value': '50'}, {'flag': '(none)', 'option': 'timeout-factor', 'value': '10'}, {'flag': '(none)', 'option': 'test-command', 'value': 'pytest'}, {'flag': '(none)', 'option': 'max-workers', 'value': 'serial'}]}, {'name': 'a numeric flag rejects values that are not positive integers', 'steps': [{'keyword': 'When', 'text': 'I run mutate4py with the flag "<flag>"', 'parameters': ['flag']}, {'keyword': 'Then', 'text': 'the invocation is a usage error'}, {'keyword': 'And', 'text': 'the command exits with a non-zero status'}, {'keyword': 'And', 'text': 'no analysis or test run occurs'}], 'examples': [{'flag': '--mutation-warning 0'}, {'flag': '--mutation-warning -3'}, {'flag': '--mutation-warning two'}, {'flag': '--timeout-factor 0'}, {'flag': '--timeout-factor 1.5'}, {'flag': '--max-workers 0'}, {'flag': '--max-workers -1'}, {'flag': '--max-workers many'}, {'flag': '--lines 0'}, {'flag': '--lines 7,-2'}, {'flag': '--lines 7,x'}]}, {'name': 'a value flag with a missing value is rejected', 'steps': [{'keyword': 'When', 'text': 'I run mutate4py with a trailing "<flag>" and no value', 'parameters': ['flag']}, {'keyword': 'Then', 'text': 'the invocation is a usage error'}, {'keyword': 'And', 'text': 'the command exits with a non-zero status'}], 'examples': [{'flag': '--mutation-warning'}, {'flag': '--timeout-factor'}, {'flag': '--test-command'}, {'flag': '--max-workers'}, {'flag': '--lines'}]}, {'name': 'a no-run mode rejects being combined with an execution option', 'steps': [{'keyword': 'When', 'text': 'I run mutate4py with "<mode>" and "<other>"', 'parameters': ['mode', 'other']}, {'keyword': 'Then', 'text': 'the invocation is a usage error'}, {'keyword': 'And', 'text': 'the command exits with a non-zero status'}], 'examples': [{'mode': '--scan', 'other': '--update-manifest'}, {'mode': '--scan', 'other': '--lines 7'}, {'mode': '--scan', 'other': '--since-last-run'}, {'mode': '--scan', 'other': '--mutate-all'}, {'mode': '--scan', 'other': '--timeout-factor 5'}, {'mode': '--scan', 'other': '--test-command "tox"'}, {'mode': '--scan', 'other': '--max-workers 4'}, {'mode': '--update-manifest', 'other': '--scan'}, {'mode': '--update-manifest', 'other': '--lines 7'}, {'mode': '--update-manifest', 'other': '--since-last-run'}, {'mode': '--update-manifest', 'other': '--mutate-all'}, {'mode': '--update-manifest', 'other': '--max-workers 4'}]}, {'name': 'combining two selection flags is a usage error', 'steps': [{'keyword': 'When', 'text': 'I run mutate4py with "<one>" and "<two>"', 'parameters': ['one', 'two']}, {'keyword': 'Then', 'text': 'the invocation is a usage error'}, {'keyword': 'And', 'text': 'the command exits with a non-zero status'}], 'examples': [{'one': '--since-last-run', 'two': '--mutate-all'}, {'one': '--since-last-run', 'two': '--lines 7'}, {'one': '--mutate-all', 'two': '--lines 7'}]}, {'name': '--max-workers is accepted alongside a selection flag', 'steps': [{'keyword': 'When', 'text': 'I run mutate4py with "--max-workers 4" and "<selection>"', 'parameters': ['selection']}, {'keyword': 'Then', 'text': 'the invocation is accepted'}], 'examples': [{'selection': '--lines 7'}, {'selection': '--since-last-run'}, {'selection': '--mutate-all'}]}, {'name': 'an unknown flag or missing source file is rejected', 'steps': [{'keyword': 'When', 'text': 'I run mutate4py described by "<invocation>"', 'parameters': ['invocation']}, {'keyword': 'Then', 'text': 'the invocation is a usage error'}, {'keyword': 'And', 'text': 'the command exits with a non-zero status'}], 'examples': [{'invocation': 'a valid file with --bogus-flag'}, {'invocation': 'no positional source file'}, {'invocation': 'a source path that does not exist'}]}, {'name': '--help short-circuits to usage even with invalid args', 'steps': [{'keyword': 'When', 'text': 'I run mutate4py with "--help" and "<alongside>"', 'parameters': ['alongside']}, {'keyword': 'Then', 'text': 'the usage summary is printed'}, {'keyword': 'And', 'text': 'the usage summary lists "--max-workers"'}, {'keyword': 'And', 'text': 'the command exits with status zero'}], 'examples': [{'alongside': '(nothing)'}, {'alongside': '--max-workers 0'}, {'alongside': '--scan --mutate-all'}]}, {'name': 'validated options are routed to the right behaviour', 'steps': [{'keyword': 'When', 'text': 'I run mutate4py with the accepted flags "<flags>"', 'parameters': ['flags']}, {'keyword': 'Then', 'text': 'the run is dispatched to the "<target>" behaviour', 'parameters': ['target']}], 'examples': [{'flags': '--scan', 'target': 'scan surface'}, {'flags': '--update-manifest', 'target': 'manifest write'}, {'flags': '(a coverage flag)', 'target': 'run loop'}]}, {'name': 'an accepted --max-workers count reaches the run dispatcher', 'steps': [{'keyword': 'When', 'text': 'I run mutate4py with the accepted flags "--max-workers 4 (a coverage flag)"'}, {'keyword': 'Then', 'text': 'the run is dispatched to the "run loop" behaviour'}, {'keyword': 'And', 'text': 'the dispatcher receives a worker count of "4"'}], 'examples': []}]

def test_the_full_flag_matrix_parses_and_applies_its_default_0():
    """Scenario: the full flag matrix parses and applies its default — example 0"""
    _s = _scenarios[0]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_full_flag_matrix_parses_and_applies_its_default_1():
    """Scenario: the full flag matrix parses and applies its default — example 1"""
    _s = _scenarios[0]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_full_flag_matrix_parses_and_applies_its_default_2():
    """Scenario: the full flag matrix parses and applies its default — example 2"""
    _s = _scenarios[0]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_full_flag_matrix_parses_and_applies_its_default_3():
    """Scenario: the full flag matrix parses and applies its default — example 3"""
    _s = _scenarios[0]
    _ex = _s['examples'][3] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_full_flag_matrix_parses_and_applies_its_default_4():
    """Scenario: the full flag matrix parses and applies its default — example 4"""
    _s = _scenarios[0]
    _ex = _s['examples'][4] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_full_flag_matrix_parses_and_applies_its_default_5():
    """Scenario: the full flag matrix parses and applies its default — example 5"""
    _s = _scenarios[0]
    _ex = _s['examples'][5] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_full_flag_matrix_parses_and_applies_its_default_6():
    """Scenario: the full flag matrix parses and applies its default — example 6"""
    _s = _scenarios[0]
    _ex = _s['examples'][6] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_full_flag_matrix_parses_and_applies_its_default_7():
    """Scenario: the full flag matrix parses and applies its default — example 7"""
    _s = _scenarios[0]
    _ex = _s['examples'][7] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_numeric_flag_rejects_values_that_are_not_positive_integers_0():
    """Scenario: a numeric flag rejects values that are not positive integers — example 0"""
    _s = _scenarios[1]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_numeric_flag_rejects_values_that_are_not_positive_integers_1():
    """Scenario: a numeric flag rejects values that are not positive integers — example 1"""
    _s = _scenarios[1]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_numeric_flag_rejects_values_that_are_not_positive_integers_2():
    """Scenario: a numeric flag rejects values that are not positive integers — example 2"""
    _s = _scenarios[1]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_numeric_flag_rejects_values_that_are_not_positive_integers_3():
    """Scenario: a numeric flag rejects values that are not positive integers — example 3"""
    _s = _scenarios[1]
    _ex = _s['examples'][3] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_numeric_flag_rejects_values_that_are_not_positive_integers_4():
    """Scenario: a numeric flag rejects values that are not positive integers — example 4"""
    _s = _scenarios[1]
    _ex = _s['examples'][4] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_numeric_flag_rejects_values_that_are_not_positive_integers_5():
    """Scenario: a numeric flag rejects values that are not positive integers — example 5"""
    _s = _scenarios[1]
    _ex = _s['examples'][5] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_numeric_flag_rejects_values_that_are_not_positive_integers_6():
    """Scenario: a numeric flag rejects values that are not positive integers — example 6"""
    _s = _scenarios[1]
    _ex = _s['examples'][6] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_numeric_flag_rejects_values_that_are_not_positive_integers_7():
    """Scenario: a numeric flag rejects values that are not positive integers — example 7"""
    _s = _scenarios[1]
    _ex = _s['examples'][7] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_numeric_flag_rejects_values_that_are_not_positive_integers_8():
    """Scenario: a numeric flag rejects values that are not positive integers — example 8"""
    _s = _scenarios[1]
    _ex = _s['examples'][8] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_numeric_flag_rejects_values_that_are_not_positive_integers_9():
    """Scenario: a numeric flag rejects values that are not positive integers — example 9"""
    _s = _scenarios[1]
    _ex = _s['examples'][9] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_numeric_flag_rejects_values_that_are_not_positive_integers_10():
    """Scenario: a numeric flag rejects values that are not positive integers — example 10"""
    _s = _scenarios[1]
    _ex = _s['examples'][10] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_value_flag_with_a_missing_value_is_rejected_0():
    """Scenario: a value flag with a missing value is rejected — example 0"""
    _s = _scenarios[2]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_value_flag_with_a_missing_value_is_rejected_1():
    """Scenario: a value flag with a missing value is rejected — example 1"""
    _s = _scenarios[2]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_value_flag_with_a_missing_value_is_rejected_2():
    """Scenario: a value flag with a missing value is rejected — example 2"""
    _s = _scenarios[2]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_value_flag_with_a_missing_value_is_rejected_3():
    """Scenario: a value flag with a missing value is rejected — example 3"""
    _s = _scenarios[2]
    _ex = _s['examples'][3] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_value_flag_with_a_missing_value_is_rejected_4():
    """Scenario: a value flag with a missing value is rejected — example 4"""
    _s = _scenarios[2]
    _ex = _s['examples'][4] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_0():
    """Scenario: a no-run mode rejects being combined with an execution option — example 0"""
    _s = _scenarios[3]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_1():
    """Scenario: a no-run mode rejects being combined with an execution option — example 1"""
    _s = _scenarios[3]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_2():
    """Scenario: a no-run mode rejects being combined with an execution option — example 2"""
    _s = _scenarios[3]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_3():
    """Scenario: a no-run mode rejects being combined with an execution option — example 3"""
    _s = _scenarios[3]
    _ex = _s['examples'][3] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_4():
    """Scenario: a no-run mode rejects being combined with an execution option — example 4"""
    _s = _scenarios[3]
    _ex = _s['examples'][4] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_5():
    """Scenario: a no-run mode rejects being combined with an execution option — example 5"""
    _s = _scenarios[3]
    _ex = _s['examples'][5] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_6():
    """Scenario: a no-run mode rejects being combined with an execution option — example 6"""
    _s = _scenarios[3]
    _ex = _s['examples'][6] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_7():
    """Scenario: a no-run mode rejects being combined with an execution option — example 7"""
    _s = _scenarios[3]
    _ex = _s['examples'][7] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_8():
    """Scenario: a no-run mode rejects being combined with an execution option — example 8"""
    _s = _scenarios[3]
    _ex = _s['examples'][8] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_9():
    """Scenario: a no-run mode rejects being combined with an execution option — example 9"""
    _s = _scenarios[3]
    _ex = _s['examples'][9] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_10():
    """Scenario: a no-run mode rejects being combined with an execution option — example 10"""
    _s = _scenarios[3]
    _ex = _s['examples'][10] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_11():
    """Scenario: a no-run mode rejects being combined with an execution option — example 11"""
    _s = _scenarios[3]
    _ex = _s['examples'][11] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_combining_two_selection_flags_is_a_usage_error_0():
    """Scenario: combining two selection flags is a usage error — example 0"""
    _s = _scenarios[4]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_combining_two_selection_flags_is_a_usage_error_1():
    """Scenario: combining two selection flags is a usage error — example 1"""
    _s = _scenarios[4]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_combining_two_selection_flags_is_a_usage_error_2():
    """Scenario: combining two selection flags is a usage error — example 2"""
    _s = _scenarios[4]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_max_workers_is_accepted_alongside_a_selection_flag_0():
    """Scenario: --max-workers is accepted alongside a selection flag — example 0"""
    _s = _scenarios[5]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_max_workers_is_accepted_alongside_a_selection_flag_1():
    """Scenario: --max-workers is accepted alongside a selection flag — example 1"""
    _s = _scenarios[5]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_max_workers_is_accepted_alongside_a_selection_flag_2():
    """Scenario: --max-workers is accepted alongside a selection flag — example 2"""
    _s = _scenarios[5]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_an_unknown_flag_or_missing_source_file_is_rejected_0():
    """Scenario: an unknown flag or missing source file is rejected — example 0"""
    _s = _scenarios[6]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_an_unknown_flag_or_missing_source_file_is_rejected_1():
    """Scenario: an unknown flag or missing source file is rejected — example 1"""
    _s = _scenarios[6]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_an_unknown_flag_or_missing_source_file_is_rejected_2():
    """Scenario: an unknown flag or missing source file is rejected — example 2"""
    _s = _scenarios[6]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_help_short_circuits_to_usage_even_with_invalid_args_0():
    """Scenario: --help short-circuits to usage even with invalid args — example 0"""
    _s = _scenarios[7]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_help_short_circuits_to_usage_even_with_invalid_args_1():
    """Scenario: --help short-circuits to usage even with invalid args — example 1"""
    _s = _scenarios[7]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_help_short_circuits_to_usage_even_with_invalid_args_2():
    """Scenario: --help short-circuits to usage even with invalid args — example 2"""
    _s = _scenarios[7]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_validated_options_are_routed_to_the_right_behaviour_0():
    """Scenario: validated options are routed to the right behaviour — example 0"""
    _s = _scenarios[8]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_validated_options_are_routed_to_the_right_behaviour_1():
    """Scenario: validated options are routed to the right behaviour — example 1"""
    _s = _scenarios[8]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_validated_options_are_routed_to_the_right_behaviour_2():
    """Scenario: validated options are routed to the right behaviour — example 2"""
    _s = _scenarios[8]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_an_accepted_max_workers_count_reaches_the_run_dispatcher_0():
    """Scenario: an accepted --max-workers count reaches the run dispatcher — example 0"""
    _s = _scenarios[9]
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
        test_the_full_flag_matrix_parses_and_applies_its_default_0()
        print('PASS test_the_full_flag_matrix_parses_and_applies_its_default_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_full_flag_matrix_parses_and_applies_its_default_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_full_flag_matrix_parses_and_applies_its_default_1()
        print('PASS test_the_full_flag_matrix_parses_and_applies_its_default_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_full_flag_matrix_parses_and_applies_its_default_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_full_flag_matrix_parses_and_applies_its_default_2()
        print('PASS test_the_full_flag_matrix_parses_and_applies_its_default_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_full_flag_matrix_parses_and_applies_its_default_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_full_flag_matrix_parses_and_applies_its_default_3()
        print('PASS test_the_full_flag_matrix_parses_and_applies_its_default_3')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_full_flag_matrix_parses_and_applies_its_default_3: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_full_flag_matrix_parses_and_applies_its_default_4()
        print('PASS test_the_full_flag_matrix_parses_and_applies_its_default_4')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_full_flag_matrix_parses_and_applies_its_default_4: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_full_flag_matrix_parses_and_applies_its_default_5()
        print('PASS test_the_full_flag_matrix_parses_and_applies_its_default_5')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_full_flag_matrix_parses_and_applies_its_default_5: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_full_flag_matrix_parses_and_applies_its_default_6()
        print('PASS test_the_full_flag_matrix_parses_and_applies_its_default_6')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_full_flag_matrix_parses_and_applies_its_default_6: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_full_flag_matrix_parses_and_applies_its_default_7()
        print('PASS test_the_full_flag_matrix_parses_and_applies_its_default_7')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_full_flag_matrix_parses_and_applies_its_default_7: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_numeric_flag_rejects_values_that_are_not_positive_integers_0()
        print('PASS test_a_numeric_flag_rejects_values_that_are_not_positive_integers_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_numeric_flag_rejects_values_that_are_not_positive_integers_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_numeric_flag_rejects_values_that_are_not_positive_integers_1()
        print('PASS test_a_numeric_flag_rejects_values_that_are_not_positive_integers_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_numeric_flag_rejects_values_that_are_not_positive_integers_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_numeric_flag_rejects_values_that_are_not_positive_integers_2()
        print('PASS test_a_numeric_flag_rejects_values_that_are_not_positive_integers_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_numeric_flag_rejects_values_that_are_not_positive_integers_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_numeric_flag_rejects_values_that_are_not_positive_integers_3()
        print('PASS test_a_numeric_flag_rejects_values_that_are_not_positive_integers_3')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_numeric_flag_rejects_values_that_are_not_positive_integers_3: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_numeric_flag_rejects_values_that_are_not_positive_integers_4()
        print('PASS test_a_numeric_flag_rejects_values_that_are_not_positive_integers_4')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_numeric_flag_rejects_values_that_are_not_positive_integers_4: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_numeric_flag_rejects_values_that_are_not_positive_integers_5()
        print('PASS test_a_numeric_flag_rejects_values_that_are_not_positive_integers_5')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_numeric_flag_rejects_values_that_are_not_positive_integers_5: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_numeric_flag_rejects_values_that_are_not_positive_integers_6()
        print('PASS test_a_numeric_flag_rejects_values_that_are_not_positive_integers_6')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_numeric_flag_rejects_values_that_are_not_positive_integers_6: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_numeric_flag_rejects_values_that_are_not_positive_integers_7()
        print('PASS test_a_numeric_flag_rejects_values_that_are_not_positive_integers_7')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_numeric_flag_rejects_values_that_are_not_positive_integers_7: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_numeric_flag_rejects_values_that_are_not_positive_integers_8()
        print('PASS test_a_numeric_flag_rejects_values_that_are_not_positive_integers_8')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_numeric_flag_rejects_values_that_are_not_positive_integers_8: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_numeric_flag_rejects_values_that_are_not_positive_integers_9()
        print('PASS test_a_numeric_flag_rejects_values_that_are_not_positive_integers_9')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_numeric_flag_rejects_values_that_are_not_positive_integers_9: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_numeric_flag_rejects_values_that_are_not_positive_integers_10()
        print('PASS test_a_numeric_flag_rejects_values_that_are_not_positive_integers_10')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_numeric_flag_rejects_values_that_are_not_positive_integers_10: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_value_flag_with_a_missing_value_is_rejected_0()
        print('PASS test_a_value_flag_with_a_missing_value_is_rejected_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_value_flag_with_a_missing_value_is_rejected_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_value_flag_with_a_missing_value_is_rejected_1()
        print('PASS test_a_value_flag_with_a_missing_value_is_rejected_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_value_flag_with_a_missing_value_is_rejected_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_value_flag_with_a_missing_value_is_rejected_2()
        print('PASS test_a_value_flag_with_a_missing_value_is_rejected_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_value_flag_with_a_missing_value_is_rejected_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_value_flag_with_a_missing_value_is_rejected_3()
        print('PASS test_a_value_flag_with_a_missing_value_is_rejected_3')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_value_flag_with_a_missing_value_is_rejected_3: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_value_flag_with_a_missing_value_is_rejected_4()
        print('PASS test_a_value_flag_with_a_missing_value_is_rejected_4')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_value_flag_with_a_missing_value_is_rejected_4: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_0()
        print('PASS test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_1()
        print('PASS test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_2()
        print('PASS test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_3()
        print('PASS test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_3')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_3: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_4()
        print('PASS test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_4')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_4: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_5()
        print('PASS test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_5')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_5: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_6()
        print('PASS test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_6')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_6: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_7()
        print('PASS test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_7')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_7: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_8()
        print('PASS test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_8')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_8: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_9()
        print('PASS test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_9')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_9: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_10()
        print('PASS test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_10')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_10: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_11()
        print('PASS test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_11')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_no_run_mode_rejects_being_combined_with_an_execution_optio_11: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_combining_two_selection_flags_is_a_usage_error_0()
        print('PASS test_combining_two_selection_flags_is_a_usage_error_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_combining_two_selection_flags_is_a_usage_error_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_combining_two_selection_flags_is_a_usage_error_1()
        print('PASS test_combining_two_selection_flags_is_a_usage_error_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_combining_two_selection_flags_is_a_usage_error_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_combining_two_selection_flags_is_a_usage_error_2()
        print('PASS test_combining_two_selection_flags_is_a_usage_error_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_combining_two_selection_flags_is_a_usage_error_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_max_workers_is_accepted_alongside_a_selection_flag_0()
        print('PASS test_max_workers_is_accepted_alongside_a_selection_flag_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_max_workers_is_accepted_alongside_a_selection_flag_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_max_workers_is_accepted_alongside_a_selection_flag_1()
        print('PASS test_max_workers_is_accepted_alongside_a_selection_flag_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_max_workers_is_accepted_alongside_a_selection_flag_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_max_workers_is_accepted_alongside_a_selection_flag_2()
        print('PASS test_max_workers_is_accepted_alongside_a_selection_flag_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_max_workers_is_accepted_alongside_a_selection_flag_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_an_unknown_flag_or_missing_source_file_is_rejected_0()
        print('PASS test_an_unknown_flag_or_missing_source_file_is_rejected_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_an_unknown_flag_or_missing_source_file_is_rejected_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_an_unknown_flag_or_missing_source_file_is_rejected_1()
        print('PASS test_an_unknown_flag_or_missing_source_file_is_rejected_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_an_unknown_flag_or_missing_source_file_is_rejected_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_an_unknown_flag_or_missing_source_file_is_rejected_2()
        print('PASS test_an_unknown_flag_or_missing_source_file_is_rejected_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_an_unknown_flag_or_missing_source_file_is_rejected_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_help_short_circuits_to_usage_even_with_invalid_args_0()
        print('PASS test_help_short_circuits_to_usage_even_with_invalid_args_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_help_short_circuits_to_usage_even_with_invalid_args_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_help_short_circuits_to_usage_even_with_invalid_args_1()
        print('PASS test_help_short_circuits_to_usage_even_with_invalid_args_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_help_short_circuits_to_usage_even_with_invalid_args_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_help_short_circuits_to_usage_even_with_invalid_args_2()
        print('PASS test_help_short_circuits_to_usage_even_with_invalid_args_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_help_short_circuits_to_usage_even_with_invalid_args_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_validated_options_are_routed_to_the_right_behaviour_0()
        print('PASS test_validated_options_are_routed_to_the_right_behaviour_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_validated_options_are_routed_to_the_right_behaviour_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_validated_options_are_routed_to_the_right_behaviour_1()
        print('PASS test_validated_options_are_routed_to_the_right_behaviour_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_validated_options_are_routed_to_the_right_behaviour_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_validated_options_are_routed_to_the_right_behaviour_2()
        print('PASS test_validated_options_are_routed_to_the_right_behaviour_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_validated_options_are_routed_to_the_right_behaviour_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_an_accepted_max_workers_count_reaches_the_run_dispatcher_0()
        print('PASS test_an_accepted_max_workers_count_reaches_the_run_dispatcher_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_an_accepted_max_workers_count_reaches_the_run_dispatcher_0: {e}')
        traceback.print_exc()
        failed += 1
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)
