import argparse
import ast
import hashlib
import json
import os
import secrets
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener


def verify(output):
    os.umask(0o077)
    clients = json.loads(Path('/run/bifang-coding-stage/fixture-clients.json').read_text())
    opener = build_opener(ProxyHandler({}))

    def call(path, method='GET', body=None, token='owner', key=None):
        headers = {}
        if token is not None:
            headers['Authorization'] = 'Bearer ' + clients[token]
        if key is not None:
            headers['Idempotency-Key'] = key
        if body is not None:
            headers['Content-Type'] = 'application/json'
        request = Request('http://127.0.0.1:8126' + path, data=json.dumps(body).encode() if body is not None else None,
                          headers=headers, method=method)
        try:
            response = opener.open(request, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    baseline = 'def valid(index, items):\n    return 0 <= index <= len(items)\n'
    corrected = 'def valid(index, items):\n    return 0 <= index < len(items)\n'
    tests = """import unittest
from bounds import valid
class BoundaryTests(unittest.TestCase):
    def test_boundaries(self):
        self.assertFalse(valid(1, [0]))
        self.assertFalse(valid(-1, [0]))
        self.assertTrue(valid(0, [0]))
"""
    payload = {'provider':'nebius','model':'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B',
               'question':'Fix only the off-by-one upper bound in bounds.py. Keep the valid function and its arguments unchanged. Make the smallest change, preserving the lower bound. Return JSON only with complete replacement content for bounds.py, no other keys than writes. Do not alter tests or claim execution.',
               'files':[{'path':'bounds.py','content':baseline},{'path':'test_bounds.py','content':tests}],
               'writable':['bounds.py'],'check_command':['python','-B','-m','unittest','discover','-v'],
               'check_timeout':30,'sharing_confirmed':True}
    key = 'private_coding_fixture_' + secrets.token_hex(12)
    marker = output.with_name('operation.json')
    record = {'phase':'submission_requested','idempotency_key':key,'request':payload,'new_model_jobs_requested':1}
    descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor,'w') as stream:
        json.dump(record,stream,indent=2)
    assert call('/health',token=None)[1].get('coding_enabled') is True
    assert call('/v1/coding/jobs',token=None)[0] == 401
    status, job = call('/v1/coding/jobs','POST',payload,key=key)
    assert status == 202
    record.update(phase='poll_existing_job',job_id=job['id'])
    marker.write_text(json.dumps(record,indent=2))
    prefix = '/v1/coding/jobs/' + job['id']
    project_path = '/v1/coding/projects/' + job['project_id']
    original = call(project_path)[1]
    duplicate = call('/v1/coding/jobs','POST',payload,key=key)
    assert duplicate[0] == 200 and duplicate[1]['id'] == job['id']
    assert call(prefix,token='other')[0] == 404
    assert call(prefix+'/patch',token='other')[0] == 404
    assert call(project_path,token='other')[0] == 404

    def wait_for(expected):
        for attempt in range(500):
            status, current = call(prefix)
            assert status == 200
            if current['status'] == expected:
                return current
            if current['status'] in {'failed','check_failed','cancelled','interrupted','rejected'}:
                record.update(phase=current['status'],error=current.get('error'))
                marker.write_text(json.dumps(record,indent=2))
                raise AssertionError('Coding fixture stopped: ' + current['status'] + ':' + str(current.get('error')))
            time.sleep(0.25)
        raise AssertionError('Keep existing job; observation window elapsed')

    job = wait_for('awaiting_write_approval')
    assert set(job['proposal']) == {'bounds.py'}
    proposed = ast.parse(job['proposal']['bounds.py'])
    if (len(proposed.body) == 1 and isinstance(proposed.body[0],ast.FunctionDef)
            and proposed.body[0].body and isinstance(proposed.body[0].body[0],ast.Expr)
            and isinstance(proposed.body[0].body[0].value,ast.Constant)
            and isinstance(proposed.body[0].body[0].value.value,str)):
        proposed.body[0].body.pop(0)
    assert ast.dump(proposed,include_attributes=False) == ast.dump(ast.parse(corrected),include_attributes=False), 'Review unexpected proposal; do not automatically approve'
    digest = job['candidate_sha256']

    def decide(action):
        status, result = call(prefix+'/decisions','POST',{'action':action,'approved':True,'candidate_sha256':digest})
        assert status == 200
        return result

    assert call(prefix+'/decisions','POST',{'action':'apply','approved':True,'candidate_sha256':digest})[0] == 409
    assert decide('writes')['status'] == 'awaiting_check_approval'
    assert call(project_path)[1] == original
    record['phase']='restart_after_write_approval'
    marker.write_text(json.dumps(record,indent=2))
    subprocess.run(['docker','restart','--time','20','bifang-coding-stage'],check=True,capture_output=True,timeout=45)
    for attempt in range(100):
        try:
            status, health = call('/health',token=None)
            if status == 200 and health.get('coding_enabled') is True:
                break
        except OSError:
            pass
        time.sleep(0.2)
    else:
        raise AssertionError('Keep existing staging container; restart health not ready')
    assert call(prefix)[1]['status']=='awaiting_check_approval'
    assert call(project_path)[1] == original
    decide('check')
    job = wait_for('verified')
    assert job['receipt']['passed'] and job['receipt']['exit_code'] == 0 and not job['receipt']['timed_out']
    assert job['receipt']['candidate_sha256'] == digest and job['receipt']['command'] == payload['check_command']
    patch = call(prefix+'/patch')[1]
    assert patch['candidate_sha256'] == digest and 'bounds.py' in patch['patch']
    assert decide('review')['status'] == 'reviewed'
    assert decide('stage')['status'] == 'staged'
    assert call(project_path)[1] == original
    assert decide('apply')['status'] == 'applied'
    applied = call(project_path)[1]
    assert applied['revision'] == digest and applied['files']['test_bounds.py'] == tests
    assert ast.dump(ast.parse(applied['files']['bounds.py']),include_attributes=False) == ast.dump(ast.parse(job['proposal']['bounds.py']),include_attributes=False)
    final = call('/v1/coding/jobs','POST',payload,key=key)
    assert final[0] == 200 and final[1]['status'] == 'applied'
    record.update(phase='applied',candidate_sha256=digest)
    marker.write_text(json.dumps(record,indent=2))
    result = {'scope':'Private loopback API, one real Token Factory proposal and actual gVisor check through persistent broker',
              'new_model_jobs_requested':1,'generation':job['generation'],'check_receipt':job['receipt'],
              'candidate_sha256':digest,'test_source_sha256':hashlib.sha256(tests.encode()).hexdigest(),
              'fixture_proposal_ast_reviewed_before_automated_decisions':True,
              'decision_method':'Explicitly scoped automated operator fixture, not a human UI walkthrough',
              'owner_isolation_passed':True,'idempotency_passed':True,'early_apply_rejected':True,
              'hosted_project_unchanged_until_separate_apply':True,'independent_tests_unchanged':True,
              'actual_api_restart_preserved_pending_approval':True,
              'hosted_apply_completed':True,'desktop_checkout_modified':False,'public_coding_enabled':False}
    output.write_text(json.dumps(result,indent=2)+'\n')
    output.chmod(0o600)
    Path('/run/bifang-coding-stage/fixture-clients.json').unlink()
    print(json.dumps(result))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Single private live coding fixture; no unbounded retries')
    parser.add_argument('--output',type=Path,required=True)
    verify(parser.parse_args().output)
