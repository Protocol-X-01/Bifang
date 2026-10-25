import subprocess
from pathlib import Path


def test_promotion_has_exact_image_gate_private_backup_and_configuration_rollback():
    path=Path(__file__).resolve().parents[1]/'deploy/aws/promote-coding-service.sh'
    subprocess.run(['bash','-n',str(path)],check=True,capture_output=True)
    content=path.read_text()
    for expected in ('trap rollback ERR','test "$active" = 0','remote-before-coding-20261025.service',
                     'python -m bifang.remote_backup','pre-coding-promotion-20261025.sqlite3',
                     'src=/run/bifang-executor,dst=/run/bifang-executor,readonly',
                     'Wants=network-online.target bifang-executor.service','127.0.0.1:8125:8125'):
        assert expected in content
    assert 'Requires=bifang-executor' not in content
    assert 'docker.sock' not in content and '--privileged' not in content
    assert content.index('systemctl stop bifang-remote.service')<content.index('python -m bifang.remote_backup')
    assert content.index('python -m bifang.remote_backup')<content.index('cat > /etc/systemd/system/bifang-remote.service')
