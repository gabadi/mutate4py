import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from acceptance.steps.parallel_workers_steps import run_step

# Scenario data baked in; APS_FEATURE_JSON overrides for gherkin mutation
_aps_override = os.environ.get('APS_FEATURE_JSON')
if _aps_override:
    with open(_aps_override) as _f:
        _ir = json.load(_f)
    _background = _ir.get('background', [])
    _scenarios = _ir.get('scenarios', [])
else:
    _background = [{'keyword': 'Given', 'text': 'a Python source file with covered mutation sites'}, {'keyword': 'And', 'text': 'a baseline test command that passes'}]
    _scenarios = [{'name': 'the worker count and site count decide serial vs parallel', 'steps': [{'keyword': 'Given', 'text': 'the file has "<sites>" selected mutation sites', 'parameters': ['sites']}, {'keyword': 'And', 'text': 'the flag supplied is "--max-workers <workers>"', 'parameters': ['workers']}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'the run takes the "<path>" path', 'parameters': ['path']}], 'examples': [{'workers': '0', 'sites': '5', 'path': 'serial'}, {'workers': '1', 'sites': '5', 'path': 'serial'}, {'workers': '4', 'sites': '1', 'path': 'serial'}, {'workers': '2', 'sites': '2', 'path': 'parallel'}, {'workers': '4', 'sites': '5', 'path': 'parallel'}]}, {'name': 'the worker count clamps to the number of selected sites', 'steps': [{'keyword': 'Given', 'text': 'the file has "<sites>" selected mutation sites', 'parameters': ['sites']}, {'keyword': 'And', 'text': 'the flag supplied is "--max-workers <workers>"', 'parameters': ['workers']}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'the output line "Mutation workers: <shown>" is printed', 'parameters': ['shown']}], 'examples': [{'workers': '8', 'sites': '3', 'shown': '3'}, {'workers': '4', 'sites': '5', 'shown': '4'}, {'workers': '2', 'sites': '2', 'shown': '2'}]}, {'name': 'the workers header line prints whenever --max-workers is over zero', 'steps': [{'keyword': 'Given', 'text': 'the file has "<sites>" selected mutation sites', 'parameters': ['sites']}, {'keyword': 'And', 'text': 'the flag supplied is "--max-workers <workers>"', 'parameters': ['workers']}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'a "Mutation workers:" line "<visibility>" printed', 'parameters': ['visibility']}], 'examples': [{'workers': '0', 'sites': '5', 'visibility': 'is not'}, {'workers': '1', 'sites': '5', 'visibility': 'is'}, {'workers': '4', 'sites': '1', 'visibility': 'is'}, {'workers': '4', 'sites': '5', 'visibility': 'is'}]}, {'name': 'the per-mutant worker token appears only on the parallel path', 'steps': [{'keyword': 'Given', 'text': 'the file has "<sites>" selected mutation sites', 'parameters': ['sites']}, {'keyword': 'And', 'text': 'the flag supplied is "--max-workers <workers>"', 'parameters': ['workers']}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'a "worker-" token "<visibility>" present in every per-mutant progress line', 'parameters': ['visibility']}], 'examples': [{'workers': '1', 'sites': '5', 'visibility': 'is not'}, {'workers': '4', 'sites': '1', 'visibility': 'is not'}, {'workers': '4', 'sites': '5', 'visibility': 'is'}]}, {'name': 'a parallel per-mutant line carries the worker token in upstream format', 'steps': [{'keyword': 'Given', 'text': 'the file has "4" selected mutation sites'}, {'keyword': 'And', 'text': 'a selected site with index "2" on line 7 in function "func/calc" mutating "a > b" to "a >= b"'}, {'keyword': 'And', 'text': 'that mutant is run by worker "3" and exits nonzero'}, {'keyword': 'And', 'text': 'the flag supplied is "--max-workers 4"'}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'the output line "[2/4] worker-3 killed line 7 a > b -> a >= b: func/calc" is printed'}], 'examples': []}, {'name': 'a parallel mutant is classified exactly as the serial path would', 'steps': [{'keyword': 'Given', 'text': 'a selected site whose mutated test run will "<outcome>"', 'parameters': ['outcome']}, {'keyword': 'And', 'text': 'the flag supplied is "--max-workers 4"'}, {'keyword': 'And', 'text': 'the file has "4" selected mutation sites'}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'the progress line for that mutant shows status "<status>"', 'parameters': ['status']}, {'keyword': 'And', 'text': 'the report counts that mutant as "<tally>"', 'parameters': ['tally']}], 'examples': [{'outcome': 'exit nonzero', 'status': 'killed', 'tally': 'Killed'}, {'outcome': 'exceed timeout', 'status': 'timeout', 'tally': 'Killed'}, {'outcome': 'exit zero', 'status': 'survived', 'tally': 'Survived'}]}, {'name': 'progress prints in arrival order but the report is deterministic', 'steps': [{'keyword': 'Given', 'text': 'the file has "3" selected mutation sites at indexes "1", "2", "3"'}, {'keyword': 'And', 'text': 'the workers finish the mutants in order "3", "1", "2"'}, {'keyword': 'And', 'text': 'the flag supplied is "--max-workers 3"'}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'the per-mutant lines appear in arrival order "3", "1", "2"'}, {'keyword': 'And', 'text': 'the "Survivors:" block lists sites sorted by stable index'}, {'keyword': 'And', 'text': 'the "Mutation Report" tallies are independent of finish order'}], 'examples': []}, {'name': 'a worker mutates its own copy and the original file is never spliced', 'steps': [{'keyword': 'Given', 'text': 'the file has "4" selected mutation sites'}, {'keyword': 'And', 'text': 'the flag supplied is "--max-workers 4"'}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'each worker has its own copy under ".mutate4py/workers/"'}, {'keyword': 'And', 'text': 'each worker copy is restored to the original after its mutant'}, {'keyword': 'And', 'text': 'the original source file is never spliced with a mutant during the run'}, {'keyword': 'And', 'text': 'no per-worker ".mutate4py.bak" file is created'}], 'examples': []}, {'name': 'the worker tree copy handles skip-list and regular entries without error', 'steps': [{'keyword': 'Given', 'text': 'the working directory contains a "<entry>" entry', 'parameters': ['entry']}, {'keyword': 'And', 'text': 'the flag supplied is "--max-workers 4"'}, {'keyword': 'And', 'text': 'the file has "4" selected mutation sites'}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'the run completes successfully'}], 'examples': [{'entry': '.git'}, {'entry': '__pycache__'}, {'entry': '.mutate4py'}, {'entry': 'src'}]}, {'name': 'the worker run root is cleaned up when the run ends', 'steps': [{'keyword': 'Given', 'text': 'the file has "4" selected mutation sites'}, {'keyword': 'And', 'text': 'the flag supplied is "--max-workers 4"'}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'a worker run root existed under ".mutate4py/workers/" during the run'}, {'keyword': 'And', 'text': 'no worker run root remains under ".mutate4py/workers/" after the run'}], 'examples': []}, {'name': 'a worker error or short result count aborts strictly', 'steps': [{'keyword': 'Given', 'text': 'the file has "4" selected mutation sites'}, {'keyword': 'And', 'text': 'the flag supplied is "--max-workers 4"'}, {'keyword': 'And', 'text': '"<failure>" occurs during the parallel run', 'parameters': ['failure']}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'the command exits with a non-zero status'}, {'keyword': 'And', 'text': 'the output contains "<message>"', 'parameters': ['message']}, {'keyword': 'And', 'text': 'no "Mutation Report" is printed'}], 'examples': [{'failure': 'a worker cannot write its file copy', 'message': 'mutation worker failed'}, {'failure': 'a worker stops before all sites run', 'message': 'mutation workers stopped after'}]}, {'name': 'a target file outside the working directory is rejected before provisioning', 'steps': [{'keyword': 'Given', 'text': 'the target file is outside the working directory'}, {'keyword': 'And', 'text': 'the flag supplied is "--max-workers 4"'}, {'keyword': 'And', 'text': 'the file has "4" selected mutation sites'}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'the command exits with a non-zero status'}, {'keyword': 'And', 'text': 'the output contains "must be inside working directory"'}, {'keyword': 'And', 'text': 'no worker root is created under ".mutate4py/workers/"'}], 'examples': []}, {'name': 'the parallel run re-embeds a fresh manifest on the original file', 'steps': [{'keyword': 'Given', 'text': 'the file has "4" selected mutation sites'}, {'keyword': 'And', 'text': 'the flag supplied is "--max-workers 4"'}, {'keyword': 'When', 'text': 'I run mutate4py mutating that file'}, {'keyword': 'Then', 'text': 'after the run the original source has no mutant spliced in'}, {'keyword': 'And', 'text': 'the original source ends with a fresh "mutate4py-manifest" footer'}, {'keyword': 'And', 'text': 'no ".mutate4py.bak" file is left behind'}], 'examples': []}]

def test_the_worker_count_and_site_count_decide_serial_vs_parallel_0():
    """Scenario: the worker count and site count decide serial vs parallel — example 0"""
    _s = _scenarios[0]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_worker_count_and_site_count_decide_serial_vs_parallel_1():
    """Scenario: the worker count and site count decide serial vs parallel — example 1"""
    _s = _scenarios[0]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_worker_count_and_site_count_decide_serial_vs_parallel_2():
    """Scenario: the worker count and site count decide serial vs parallel — example 2"""
    _s = _scenarios[0]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_worker_count_and_site_count_decide_serial_vs_parallel_3():
    """Scenario: the worker count and site count decide serial vs parallel — example 3"""
    _s = _scenarios[0]
    _ex = _s['examples'][3] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_worker_count_and_site_count_decide_serial_vs_parallel_4():
    """Scenario: the worker count and site count decide serial vs parallel — example 4"""
    _s = _scenarios[0]
    _ex = _s['examples'][4] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_worker_count_clamps_to_the_number_of_selected_sites_0():
    """Scenario: the worker count clamps to the number of selected sites — example 0"""
    _s = _scenarios[1]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_worker_count_clamps_to_the_number_of_selected_sites_1():
    """Scenario: the worker count clamps to the number of selected sites — example 1"""
    _s = _scenarios[1]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_worker_count_clamps_to_the_number_of_selected_sites_2():
    """Scenario: the worker count clamps to the number of selected sites — example 2"""
    _s = _scenarios[1]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_workers_header_line_prints_whenever_max_workers_is_over__0():
    """Scenario: the workers header line prints whenever --max-workers is over zero — example 0"""
    _s = _scenarios[2]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_workers_header_line_prints_whenever_max_workers_is_over__1():
    """Scenario: the workers header line prints whenever --max-workers is over zero — example 1"""
    _s = _scenarios[2]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_workers_header_line_prints_whenever_max_workers_is_over__2():
    """Scenario: the workers header line prints whenever --max-workers is over zero — example 2"""
    _s = _scenarios[2]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_workers_header_line_prints_whenever_max_workers_is_over__3():
    """Scenario: the workers header line prints whenever --max-workers is over zero — example 3"""
    _s = _scenarios[2]
    _ex = _s['examples'][3] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_per_mutant_worker_token_appears_only_on_the_parallel_pat_0():
    """Scenario: the per-mutant worker token appears only on the parallel path — example 0"""
    _s = _scenarios[3]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_per_mutant_worker_token_appears_only_on_the_parallel_pat_1():
    """Scenario: the per-mutant worker token appears only on the parallel path — example 1"""
    _s = _scenarios[3]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_per_mutant_worker_token_appears_only_on_the_parallel_pat_2():
    """Scenario: the per-mutant worker token appears only on the parallel path — example 2"""
    _s = _scenarios[3]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_parallel_per_mutant_line_carries_the_worker_token_in_upstr_0():
    """Scenario: a parallel per-mutant line carries the worker token in upstream format — example 0"""
    _s = _scenarios[4]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_parallel_mutant_is_classified_exactly_as_the_serial_path_w_0():
    """Scenario: a parallel mutant is classified exactly as the serial path would — example 0"""
    _s = _scenarios[5]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_parallel_mutant_is_classified_exactly_as_the_serial_path_w_1():
    """Scenario: a parallel mutant is classified exactly as the serial path would — example 1"""
    _s = _scenarios[5]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_parallel_mutant_is_classified_exactly_as_the_serial_path_w_2():
    """Scenario: a parallel mutant is classified exactly as the serial path would — example 2"""
    _s = _scenarios[5]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_progress_prints_in_arrival_order_but_the_report_is_determini_0():
    """Scenario: progress prints in arrival order but the report is deterministic — example 0"""
    _s = _scenarios[6]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_worker_mutates_its_own_copy_and_the_original_file_is_never_0():
    """Scenario: a worker mutates its own copy and the original file is never spliced — example 0"""
    _s = _scenarios[7]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_worker_tree_copy_handles_skip_list_and_regular_entries_w_0():
    """Scenario: the worker tree copy handles skip-list and regular entries without error — example 0"""
    _s = _scenarios[8]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_worker_tree_copy_handles_skip_list_and_regular_entries_w_1():
    """Scenario: the worker tree copy handles skip-list and regular entries without error — example 1"""
    _s = _scenarios[8]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_worker_tree_copy_handles_skip_list_and_regular_entries_w_2():
    """Scenario: the worker tree copy handles skip-list and regular entries without error — example 2"""
    _s = _scenarios[8]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_worker_tree_copy_handles_skip_list_and_regular_entries_w_3():
    """Scenario: the worker tree copy handles skip-list and regular entries without error — example 3"""
    _s = _scenarios[8]
    _ex = _s['examples'][3] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_worker_run_root_is_cleaned_up_when_the_run_ends_0():
    """Scenario: the worker run root is cleaned up when the run ends — example 0"""
    _s = _scenarios[9]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_worker_error_or_short_result_count_aborts_strictly_0():
    """Scenario: a worker error or short result count aborts strictly — example 0"""
    _s = _scenarios[10]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_worker_error_or_short_result_count_aborts_strictly_1():
    """Scenario: a worker error or short result count aborts strictly — example 1"""
    _s = _scenarios[10]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_a_target_file_outside_the_working_directory_is_rejected_befo_0():
    """Scenario: a target file outside the working directory is rejected before provisioning — example 0"""
    _s = _scenarios[11]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_the_parallel_run_re_embeds_a_fresh_manifest_on_the_original__0():
    """Scenario: the parallel run re-embeds a fresh manifest on the original file — example 0"""
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
        test_the_worker_count_and_site_count_decide_serial_vs_parallel_0()
        print('PASS test_the_worker_count_and_site_count_decide_serial_vs_parallel_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_worker_count_and_site_count_decide_serial_vs_parallel_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_worker_count_and_site_count_decide_serial_vs_parallel_1()
        print('PASS test_the_worker_count_and_site_count_decide_serial_vs_parallel_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_worker_count_and_site_count_decide_serial_vs_parallel_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_worker_count_and_site_count_decide_serial_vs_parallel_2()
        print('PASS test_the_worker_count_and_site_count_decide_serial_vs_parallel_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_worker_count_and_site_count_decide_serial_vs_parallel_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_worker_count_and_site_count_decide_serial_vs_parallel_3()
        print('PASS test_the_worker_count_and_site_count_decide_serial_vs_parallel_3')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_worker_count_and_site_count_decide_serial_vs_parallel_3: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_worker_count_and_site_count_decide_serial_vs_parallel_4()
        print('PASS test_the_worker_count_and_site_count_decide_serial_vs_parallel_4')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_worker_count_and_site_count_decide_serial_vs_parallel_4: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_worker_count_clamps_to_the_number_of_selected_sites_0()
        print('PASS test_the_worker_count_clamps_to_the_number_of_selected_sites_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_worker_count_clamps_to_the_number_of_selected_sites_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_worker_count_clamps_to_the_number_of_selected_sites_1()
        print('PASS test_the_worker_count_clamps_to_the_number_of_selected_sites_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_worker_count_clamps_to_the_number_of_selected_sites_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_worker_count_clamps_to_the_number_of_selected_sites_2()
        print('PASS test_the_worker_count_clamps_to_the_number_of_selected_sites_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_worker_count_clamps_to_the_number_of_selected_sites_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_workers_header_line_prints_whenever_max_workers_is_over__0()
        print('PASS test_the_workers_header_line_prints_whenever_max_workers_is_over__0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_workers_header_line_prints_whenever_max_workers_is_over__0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_workers_header_line_prints_whenever_max_workers_is_over__1()
        print('PASS test_the_workers_header_line_prints_whenever_max_workers_is_over__1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_workers_header_line_prints_whenever_max_workers_is_over__1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_workers_header_line_prints_whenever_max_workers_is_over__2()
        print('PASS test_the_workers_header_line_prints_whenever_max_workers_is_over__2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_workers_header_line_prints_whenever_max_workers_is_over__2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_workers_header_line_prints_whenever_max_workers_is_over__3()
        print('PASS test_the_workers_header_line_prints_whenever_max_workers_is_over__3')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_workers_header_line_prints_whenever_max_workers_is_over__3: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_per_mutant_worker_token_appears_only_on_the_parallel_pat_0()
        print('PASS test_the_per_mutant_worker_token_appears_only_on_the_parallel_pat_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_per_mutant_worker_token_appears_only_on_the_parallel_pat_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_per_mutant_worker_token_appears_only_on_the_parallel_pat_1()
        print('PASS test_the_per_mutant_worker_token_appears_only_on_the_parallel_pat_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_per_mutant_worker_token_appears_only_on_the_parallel_pat_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_per_mutant_worker_token_appears_only_on_the_parallel_pat_2()
        print('PASS test_the_per_mutant_worker_token_appears_only_on_the_parallel_pat_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_per_mutant_worker_token_appears_only_on_the_parallel_pat_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_parallel_per_mutant_line_carries_the_worker_token_in_upstr_0()
        print('PASS test_a_parallel_per_mutant_line_carries_the_worker_token_in_upstr_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_parallel_per_mutant_line_carries_the_worker_token_in_upstr_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_parallel_mutant_is_classified_exactly_as_the_serial_path_w_0()
        print('PASS test_a_parallel_mutant_is_classified_exactly_as_the_serial_path_w_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_parallel_mutant_is_classified_exactly_as_the_serial_path_w_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_parallel_mutant_is_classified_exactly_as_the_serial_path_w_1()
        print('PASS test_a_parallel_mutant_is_classified_exactly_as_the_serial_path_w_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_parallel_mutant_is_classified_exactly_as_the_serial_path_w_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_parallel_mutant_is_classified_exactly_as_the_serial_path_w_2()
        print('PASS test_a_parallel_mutant_is_classified_exactly_as_the_serial_path_w_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_parallel_mutant_is_classified_exactly_as_the_serial_path_w_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_progress_prints_in_arrival_order_but_the_report_is_determini_0()
        print('PASS test_progress_prints_in_arrival_order_but_the_report_is_determini_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_progress_prints_in_arrival_order_but_the_report_is_determini_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_worker_mutates_its_own_copy_and_the_original_file_is_never_0()
        print('PASS test_a_worker_mutates_its_own_copy_and_the_original_file_is_never_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_worker_mutates_its_own_copy_and_the_original_file_is_never_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_worker_tree_copy_handles_skip_list_and_regular_entries_w_0()
        print('PASS test_the_worker_tree_copy_handles_skip_list_and_regular_entries_w_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_worker_tree_copy_handles_skip_list_and_regular_entries_w_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_worker_tree_copy_handles_skip_list_and_regular_entries_w_1()
        print('PASS test_the_worker_tree_copy_handles_skip_list_and_regular_entries_w_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_worker_tree_copy_handles_skip_list_and_regular_entries_w_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_worker_tree_copy_handles_skip_list_and_regular_entries_w_2()
        print('PASS test_the_worker_tree_copy_handles_skip_list_and_regular_entries_w_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_worker_tree_copy_handles_skip_list_and_regular_entries_w_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_worker_tree_copy_handles_skip_list_and_regular_entries_w_3()
        print('PASS test_the_worker_tree_copy_handles_skip_list_and_regular_entries_w_3')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_worker_tree_copy_handles_skip_list_and_regular_entries_w_3: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_worker_run_root_is_cleaned_up_when_the_run_ends_0()
        print('PASS test_the_worker_run_root_is_cleaned_up_when_the_run_ends_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_worker_run_root_is_cleaned_up_when_the_run_ends_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_worker_error_or_short_result_count_aborts_strictly_0()
        print('PASS test_a_worker_error_or_short_result_count_aborts_strictly_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_worker_error_or_short_result_count_aborts_strictly_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_worker_error_or_short_result_count_aborts_strictly_1()
        print('PASS test_a_worker_error_or_short_result_count_aborts_strictly_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_worker_error_or_short_result_count_aborts_strictly_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_a_target_file_outside_the_working_directory_is_rejected_befo_0()
        print('PASS test_a_target_file_outside_the_working_directory_is_rejected_befo_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_a_target_file_outside_the_working_directory_is_rejected_befo_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_the_parallel_run_re_embeds_a_fresh_manifest_on_the_original__0()
        print('PASS test_the_parallel_run_re_embeds_a_fresh_manifest_on_the_original__0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_the_parallel_run_re_embeds_a_fresh_manifest_on_the_original__0: {e}')
        traceback.print_exc()
        failed += 1
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)
