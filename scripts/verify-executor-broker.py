import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import subprocess
import uuid
from pathlib import Path


async def verify(options):
    if os.geteuid() != 0:
        raise RuntimeError("Use the isolated host operator")
    specification = importlib.util.spec_from_file_location("bifang_broker_verification", options.module)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    settings = json.loads(Path(options.configuration).read_text())
    executor = module.Executor(**settings)
    await executor.verify_runtime()
    directory = Path('/run/bifang-executor')
    assert directory.stat().st_uid == 0 and directory.stat().st_gid == 10001
    assert directory.stat().st_mode & 0o777 == 0o750
    previous_inode = directory.stat().st_ino
    before_pid = int(await asyncio.to_thread(subprocess.check_output,['systemctl','show','bifang-executor','--property=MainPID','--value'], text=True))
    assert before_pid > 0
    assert not await executor.control('ps','--all','--quiet','--filter','label=bifang.executor=1')
    name = 'bifang-ipc-client-' + uuid.uuid4().hex
    code = """import asyncio,hashlib,importlib.util,json,os,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('client','/client.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
async def scenario():
    assert os.getuid()==10001
    assert not Path('/var/run/docker.sock').exists()
    client=module.BrokerClient('/run/bifang-executor/check.sock')
    await client.verify_peer()
    inode=Path('/run/bifang-executor').stat().st_ino
    first=await client({'first.py':"print('first-private-check')\\n"},['python','-B','first.py'],30)
    assert first['exit_code']==0
    assert first['output_sha256']==hashlib.sha256(b'first-private-check\\n').hexdigest()
    print('CLIENT_READY',flush=True)
    assert (await asyncio.to_thread(sys.stdin.readline)).strip()=='continue'
    await client.verify_peer()
    second=await client({'second.py':"print('second-private-check')\\n"},['python','-B','second.py'],30)
    assert second['exit_code']==0
    assert second['output_sha256']==hashlib.sha256(b'second-private-check\\n').hexdigest()
    assert Path('/run/bifang-executor').stat().st_ino==inode
    print(json.dumps({'api_client_uid':os.getuid(),'server_peer_uid_verified':0,'same_bind_mount_after_restart':True}),flush=True)
asyncio.run(scenario())
"""
    process = await asyncio.create_subprocess_exec('/usr/bin/docker','run','--rm','--interactive','--name',name,
        '--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--user','10001:10001',
        '--memory','128m','--cpus','1','--pids-limit','64','--tmpfs','/tmp:rw,nosuid,noexec,size=16m',
        '--mount','type=bind,src=/run/bifang-executor,dst=/run/bifang-executor,readonly',
        '--mount','type=bind,src='+str(Path(options.module).resolve())+',dst=/client.py,readonly',
        '--entrypoint','/usr/local/bin/python',settings['image'],'-I','-c',code,
        env=executor.environment,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    hanging = None
    try:
        line = await asyncio.wait_for(process.stdout.readline(), timeout=40)
        if line != b'CLIENT_READY\n':
            error = await process.stderr.read(4000)
            raise RuntimeError('API identity fixture failed: ' + error.decode(errors='replace'))
        client = module.BrokerClient('/run/bifang-executor/check.sock')
        hanging = asyncio.create_task(client({'hang.py':'import time\ntime.sleep(60)\n'},['python','-B','hang.py'],60))
        for attempt in range(60):
            if await executor.control('ps','--quiet','--filter','label=bifang.executor=1'):
                break
            if hanging.done():
                await hanging
                raise AssertionError('Expected a running check before broker crash')
            await asyncio.sleep(0.2)
        else:
            raise AssertionError('No running execution container observed')
        await asyncio.to_thread(subprocess.run,['systemctl','kill','--kill-who=main','--signal=SIGKILL','bifang-executor'],
                                capture_output=True,check=True,timeout=10)
        for attempt in range(100):
            try:
                current_pid = int(await asyncio.to_thread(subprocess.check_output,['systemctl','show','bifang-executor','--property=MainPID','--value'],text=True))
                if current_pid > 0 and current_pid != before_pid:
                    await client.verify_peer()
                    break
            except (OSError, ValueError, RuntimeError):
                pass
            await asyncio.sleep(0.2)
        else:
            raise AssertionError('Broker did not recover after forced termination')
        assert not await executor.control('ps','--all','--quiet','--filter','label=bifang.executor=1')
        assert not list(executor.scratch.iterdir())
        assert directory.stat().st_ino == previous_inode
        process.stdin.write(b'continue\n')
        await process.stdin.drain()
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=40)
        assert process.returncode == 0, stderr.decode(errors='replace')[:2000]
        observed = json.loads(stdout)
        assert observed['api_client_uid'] == 10001 and observed['same_bind_mount_after_restart'] is True
        result = {**observed,'scope':'Actual persistent broker, unprivileged API identity and forced restart proof',
                  'executor_module_sha256':hashlib.sha256(Path(options.module).read_bytes()).hexdigest(),
                  'execution_image':settings['image'],'broker_main_pid_changed':True,
                  'running_check_cleaned_after_broker_sigkill':True,'scratch_empty_after_crash':True,
                  'socket_parent_inode_preserved':True,'no_docker_socket_in_api_client':True,
                  'provider_calls':0,'public_coding_enabled':False}
        output = Path(options.output)
        output.write_text(json.dumps(result,indent=2)+'\n')
        output.chmod(0o600)
        print(json.dumps(result))
    finally:
        if hanging is not None:
            if not hanging.done():
                hanging.cancel()
            await asyncio.gather(hanging,return_exceptions=True)
        if process.returncode is None:
            process.kill()
            await process.wait()
        remaining = await executor.control('ps','--all','--quiet','--filter','name='+name)
        if remaining.strip():
            await executor.control('rm','--force',name)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Verify private broker lifecycle with synthetic source; no inference')
    parser.add_argument('--module',required=True)
    parser.add_argument('--configuration',required=True)
    parser.add_argument('--output',required=True)
    asyncio.run(verify(parser.parse_args()))
