import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener


def verify(image):
    if os.geteuid()!=0:
        raise RuntimeError('Use the isolated host operator')

    def docker(*arguments):
        return subprocess.check_output(['docker',*arguments],text=True,timeout=20).strip()

    assert docker('inspect','--format','{{.Image}}','bifang-remote')==image
    before=docker('inspect','--format','{{.Id}}','bifang-remote')
    inode=Path('/run/bifang-executor').stat().st_ino
    check="import sqlite3; connection=sqlite3.connect('file:/var/lib/bifang/review-jobs.sqlite3?mode=ro',uri=True); assert connection.execute('SELECT count(*) FROM coding_jobs').fetchone()[0]==0; assert connection.execute(\"SELECT count(*) FROM review_jobs WHERE status IN ('queued','running','cancelling')\").fetchone()[0]==0; connection.close()"
    docker('exec','bifang-remote','python','-c',check)
    subprocess.run(['systemctl','restart','bifang-executor.service'],check=True,capture_output=True,timeout=45)
    opener=build_opener(ProxyHandler({}))
    for attempt in range(100):
        try:
            with opener.open('http://127.0.0.1:8125/health',timeout=2) as response:
                value=json.load(response)
            if value.get('status')=='ok' and value.get('coding_enabled') is True:
                break
        except (OSError,ValueError):
            pass
        time.sleep(0.2)
    else:
        raise AssertionError('Retain current service state; post-restart health unavailable')
    assert docker('inspect','--format','{{.Id}}','bifang-remote')==before
    assert Path('/run/bifang-executor').stat().st_ino==inode
    assert not Path('/run/bifang/service.env').exists()
    subprocess.run(['systemctl','is-active','--quiet','bifang-remote','nginx'],check=True,timeout=10)
    return {'scope':'Actual idle production API recovery after only its private broker restarted',
            'api_image_id':image,'api_container_unchanged':True,'socket_parent_inode_preserved':True,
            'coding_health_recovered':True,'ephemeral_environment_absent':True,'new_inference_requests':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--image',required=True)
    print(json.dumps(verify(parser.parse_args().image)))
