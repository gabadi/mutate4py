import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from acceptance.steps.parallel_workers_qa_steps import run_step

# Scenario data baked in; APS_FEATURE_JSON overrides for gherkin mutation
_aps_override = os.environ.get('APS_FEATURE_JSON')
if _aps_override:
    with open(_aps_override) as _f:
        _ir = json.load(_f)
    _background = _ir.get('background', [])
    _scenarios = _ir.get('scenarios', [])
else:
    _background = [{'keyword': 'Given', 'text': 'a temp working directory the QA agent owns and tears down'}, {'keyword': 'And', 'text': 'a Python source fixture "calc.py" with covered mutation sites on lines "3,5,7,9"'}, {'keyword': 'And', 'text': 'a hand-written LCOV "cov.info" with SF matching "calc.py" and DA hits on lines "3,5,7,9"'}, {'keyword': 'And', 'text': 'a fake test command "runtests.sh" the QA agent scripts per outcome'}]
    _scenarios = [{'name': 'QA confirms the Mutation workers line prints whenever --max-workers is over zero', 'steps': [{'keyword': 'Given', 'text': '"runtests.sh" exits nonzero for every mutant while the baseline passes'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers <workers> --test-command ./runtests.sh --timeout-factor 2"', 'parameters': ['workers']}, {'keyword': 'Then', 'text': 'stdout "<containsLine>" contain "Mutation workers:"', 'parameters': ['containsLine']}, {'keyword': 'And', 'text': 'the exit status is zero'}], 'examples': [{'workers': '0', 'containsLine': 'does not'}, {'workers': '1', 'containsLine': 'does'}, {'workers': '4', 'containsLine': 'does'}]}, {'name': 'QA confirms worker-<k> tokens appear only when the parallel engine runs', 'steps': [{'keyword': 'Given', 'text': '"runtests.sh" exits nonzero for every mutant while the baseline passes'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers <workers> --test-command ./runtests.sh --timeout-factor 2"', 'parameters': ['workers']}, {'keyword': 'Then', 'text': 'every per-mutant line in stdout "<containsToken>" contain a "worker-" token', 'parameters': ['containsToken']}], 'examples': [{'workers': '1', 'containsToken': 'does not'}, {'workers': '4', 'containsToken': 'does'}]}, {'name': 'QA sees --max-workers clamped to the selected-site count on the workers line', 'steps': [{'keyword': 'Given', 'text': '"runtests.sh" exits nonzero for every mutant while the baseline passes'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers 9 --test-command ./runtests.sh --timeout-factor 2"'}, {'keyword': 'Then', 'text': 'stdout contains "Selected mutation sites: 4"'}, {'keyword': 'And', 'text': 'stdout contains "Mutation workers: 4"'}], 'examples': []}, {'name': 'QA drives killed / survived / timeout under --max-workers and sees the status', 'steps': [{'keyword': 'Given', 'text': '"runtests.sh" makes the mutated run "<outcome>" while the baseline passes', 'parameters': ['outcome']}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers 4 --test-command ./runtests.sh --timeout-factor 2"'}, {'keyword': 'Then', 'text': 'stdout contains a per-mutant line matching "worker-<k> <status> line " for that mutant', 'parameters': ['k', 'status']}, {'keyword': 'And', 'text': 'the exit status is zero'}], 'examples': [{'outcome': 'exit nonzero', 'status': 'killed'}, {'outcome': 'exit zero', 'status': 'survived'}, {'outcome': 'sleep past timeout', 'status': 'timeout'}]}, {'name': 'QA sees the same report tallies and survivor set across repeated parallel runs', 'steps': [{'keyword': 'Given', 'text': '"runtests.sh" makes "1" of the 4 mutants exit zero and the rest exit nonzero'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers 4 --test-command ./runtests.sh --timeout-factor 2" twice'}, {'keyword': 'Then', 'text': 'both runs print "Killed: 3"'}, {'keyword': 'And', 'text': 'both runs print "Survived: 1"'}, {'keyword': 'And', 'text': 'both runs list the same site under "Survivors:"'}], 'examples': []}, {'name': 'QA confirms the test command runs under a per-worker copy, not the original dir', 'steps': [{'keyword': 'Given', 'text': '"runtests.sh" records its working directory to a sentinel and exits nonzero'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers 4 --test-command ./runtests.sh --timeout-factor 2"'}, {'keyword': 'Then', 'text': 'the recorded working directories are under ".mutate4py/workers/"'}, {'keyword': 'And', 'text': 'none of the recorded working directories is the original working directory'}], 'examples': []}, {'name': 'QA sees the worker tree present during the run and removed afterward', 'steps': [{'keyword': 'Given', 'text': '"runtests.sh" checks for a ".mutate4py/workers/" tree on its first call and exits nonzero'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers 4 --test-command ./runtests.sh --timeout-factor 2"'}, {'keyword': 'Then', 'text': '"runtests.sh" observed a ".mutate4py/workers/" tree during the run'}, {'keyword': 'And', 'text': 'no ".mutate4py/workers/" tree exists in the working directory after the run'}], 'examples': []}, {'name': 'QA confirms the original source is byte-restored with a fresh manifest after a parallel run', 'steps': [{'keyword': 'Given', 'text': 'the bytes of "calc.py" before any manifest footer are recorded'}, {'keyword': 'And', 'text': '"runtests.sh" exits nonzero for every mutant'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers 4 --test-command ./runtests.sh --timeout-factor 2"'}, {'keyword': 'Then', 'text': 'the body of "calc.py" above the manifest footer is unchanged'}, {'keyword': 'And', 'text': '"calc.py" ends with a "mutate4py-manifest-begin" / "mutate4py-manifest-end" footer'}, {'keyword': 'And', 'text': 'no ".mutate4py.bak" file exists in the working directory'}], 'examples': []}, {'name': 'QA sees a scripted worker failure abort the parallel run with no report', 'steps': [{'keyword': 'Given', 'text': '"runtests.sh" exits nonzero for every mutant while the baseline passes'}, {'keyword': 'And', 'text': 'one worker copy is made unwritable so its restore fails'}, {'keyword': 'When', 'text': 'the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers 4 --test-command ./runtests.sh --timeout-factor 2"'}, {'keyword': 'Then', 'text': 'the exit status is non-zero'}, {'keyword': 'And', 'text': 'stdout does not contain "Mutation Report"'}], 'examples': []}]

def test_qa_confirms_the_mutation_workers_line_prints_whenever_max_wo_0():
    """Scenario: QA confirms the Mutation workers line prints whenever --max-workers is over zero — example 0"""
    _s = _scenarios[0]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_the_mutation_workers_line_prints_whenever_max_wo_1():
    """Scenario: QA confirms the Mutation workers line prints whenever --max-workers is over zero — example 1"""
    _s = _scenarios[0]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_the_mutation_workers_line_prints_whenever_max_wo_2():
    """Scenario: QA confirms the Mutation workers line prints whenever --max-workers is over zero — example 2"""
    _s = _scenarios[0]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_worker_k_tokens_appear_only_when_the_parallel_en_0():
    """Scenario: QA confirms worker-<k> tokens appear only when the parallel engine runs — example 0"""
    _s = _scenarios[1]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_worker_k_tokens_appear_only_when_the_parallel_en_1():
    """Scenario: QA confirms worker-<k> tokens appear only when the parallel engine runs — example 1"""
    _s = _scenarios[1]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_sees_max_workers_clamped_to_the_selected_site_count_on_th_0():
    """Scenario: QA sees --max-workers clamped to the selected-site count on the workers line — example 0"""
    _s = _scenarios[2]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_drives_killed_survived_timeout_under_max_workers_and_sees_0():
    """Scenario: QA drives killed / survived / timeout under --max-workers and sees the status — example 0"""
    _s = _scenarios[3]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_drives_killed_survived_timeout_under_max_workers_and_sees_1():
    """Scenario: QA drives killed / survived / timeout under --max-workers and sees the status — example 1"""
    _s = _scenarios[3]
    _ex = _s['examples'][1] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_drives_killed_survived_timeout_under_max_workers_and_sees_2():
    """Scenario: QA drives killed / survived / timeout under --max-workers and sees the status — example 2"""
    _s = _scenarios[3]
    _ex = _s['examples'][2] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_sees_the_same_report_tallies_and_survivor_set_across_repe_0():
    """Scenario: QA sees the same report tallies and survivor set across repeated parallel runs — example 0"""
    _s = _scenarios[4]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_the_test_command_runs_under_a_per_worker_copy_no_0():
    """Scenario: QA confirms the test command runs under a per-worker copy, not the original dir — example 0"""
    _s = _scenarios[5]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_sees_the_worker_tree_present_during_the_run_and_removed_a_0():
    """Scenario: QA sees the worker tree present during the run and removed afterward — example 0"""
    _s = _scenarios[6]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_confirms_the_original_source_is_byte_restored_with_a_fres_0():
    """Scenario: QA confirms the original source is byte-restored with a fresh manifest after a parallel run — example 0"""
    _s = _scenarios[7]
    _ex = _s['examples'][0] if _s.get('examples') else {}
    for _st in _background:
        run_step(_st['keyword'], _st['text'], _ex)
    for _st in _s['steps']:
        _txt = _st['text']
        for _k, _v in _ex.items():
            _txt = _txt.replace('<' + _k + '>', _v)
        run_step(_st['keyword'], _txt, _ex)

def test_qa_sees_a_scripted_worker_failure_abort_the_parallel_run_wit_0():
    """Scenario: QA sees a scripted worker failure abort the parallel run with no report — example 0"""
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
        test_qa_confirms_the_mutation_workers_line_prints_whenever_max_wo_0()
        print('PASS test_qa_confirms_the_mutation_workers_line_prints_whenever_max_wo_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_the_mutation_workers_line_prints_whenever_max_wo_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_the_mutation_workers_line_prints_whenever_max_wo_1()
        print('PASS test_qa_confirms_the_mutation_workers_line_prints_whenever_max_wo_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_the_mutation_workers_line_prints_whenever_max_wo_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_the_mutation_workers_line_prints_whenever_max_wo_2()
        print('PASS test_qa_confirms_the_mutation_workers_line_prints_whenever_max_wo_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_the_mutation_workers_line_prints_whenever_max_wo_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_worker_k_tokens_appear_only_when_the_parallel_en_0()
        print('PASS test_qa_confirms_worker_k_tokens_appear_only_when_the_parallel_en_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_worker_k_tokens_appear_only_when_the_parallel_en_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_worker_k_tokens_appear_only_when_the_parallel_en_1()
        print('PASS test_qa_confirms_worker_k_tokens_appear_only_when_the_parallel_en_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_worker_k_tokens_appear_only_when_the_parallel_en_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_sees_max_workers_clamped_to_the_selected_site_count_on_th_0()
        print('PASS test_qa_sees_max_workers_clamped_to_the_selected_site_count_on_th_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_sees_max_workers_clamped_to_the_selected_site_count_on_th_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_drives_killed_survived_timeout_under_max_workers_and_sees_0()
        print('PASS test_qa_drives_killed_survived_timeout_under_max_workers_and_sees_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_drives_killed_survived_timeout_under_max_workers_and_sees_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_drives_killed_survived_timeout_under_max_workers_and_sees_1()
        print('PASS test_qa_drives_killed_survived_timeout_under_max_workers_and_sees_1')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_drives_killed_survived_timeout_under_max_workers_and_sees_1: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_drives_killed_survived_timeout_under_max_workers_and_sees_2()
        print('PASS test_qa_drives_killed_survived_timeout_under_max_workers_and_sees_2')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_drives_killed_survived_timeout_under_max_workers_and_sees_2: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_sees_the_same_report_tallies_and_survivor_set_across_repe_0()
        print('PASS test_qa_sees_the_same_report_tallies_and_survivor_set_across_repe_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_sees_the_same_report_tallies_and_survivor_set_across_repe_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_the_test_command_runs_under_a_per_worker_copy_no_0()
        print('PASS test_qa_confirms_the_test_command_runs_under_a_per_worker_copy_no_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_the_test_command_runs_under_a_per_worker_copy_no_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_sees_the_worker_tree_present_during_the_run_and_removed_a_0()
        print('PASS test_qa_sees_the_worker_tree_present_during_the_run_and_removed_a_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_sees_the_worker_tree_present_during_the_run_and_removed_a_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_confirms_the_original_source_is_byte_restored_with_a_fres_0()
        print('PASS test_qa_confirms_the_original_source_is_byte_restored_with_a_fres_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_confirms_the_original_source_is_byte_restored_with_a_fres_0: {e}')
        traceback.print_exc()
        failed += 1
    try:
        test_qa_sees_a_scripted_worker_failure_abort_the_parallel_run_wit_0()
        print('PASS test_qa_sees_a_scripted_worker_failure_abort_the_parallel_run_wit_0')
        passed += 1
    except Exception as e:
        print(f'FAIL test_qa_sees_a_scripted_worker_failure_abort_the_parallel_run_wit_0: {e}')
        traceback.print_exc()
        failed += 1
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(0 if failed == 0 else 1)
