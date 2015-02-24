import os
import time

import docker.errors
import pytest

from unittest.mock import ANY

from epicbox.sandboxes import run, working_directory, \
                              _start_sandbox, _write_files


def test_run_python(profile):
    command = 'python3 -c \'import sys; ' \
              'print("stdout data"); print("stderr data", file=sys.stderr)\''
    result = run(profile.name, command)

    expected_result = {
        'exit_code': 0,
        'stdout': b'stdout data\n',
        'stderr': b'stderr data\n',
        'duration': ANY,
        'timeout': False,
        'oom_killed': False,
    }
    assert result == expected_result
    assert result['duration'] > 0


def test_run_unknown_profile():
    with pytest.raises(ValueError):
        run('unknown', 'true')


def test_run_non_zero_exit(profile):
    result = run(profile.name, 'false')

    assert result['exit_code'] == 1


def test_run_real_timeout(profile):
    result = run(profile.name, 'sleep 100', limits={'realtime': 1})

    assert result['timeout'] is True
    assert result['exit_code'] is None


def test_run_cpu_timeout(profile):
    start_time = time.time()

    result = run(profile.name, 'cat /dev/urandom > /dev/null',
                 limits={'cputime': 1, 'realtime': 10})

    assert result['timeout'] is True
    assert result['exit_code'] is not None
    realtime_duration = time.time() - start_time
    assert realtime_duration < 10


def test_run_memory_limit(profile):
    result = run(profile.name, 'python3 -c "[1] * 10 ** 6"',
                 limits={'cputime': 10, 'memory': 4})

    assert result['oom_killed'] is True
    assert result['timeout'] is False


def test_run_user_processes_limit(profile):
    result = run(profile.name, 'ls', limits={'numprocs': 1, 'cputime': 30})

    assert result['exit_code']
    assert b'fork: retry: No child processes' in result['stderr']


def test_run_upload_files(profile, skip_if_remote_docker):
    files = [
        {'name': 'main.py', 'content': b'print(open("file.txt").read())'},
        {'name': 'file.txt', 'content': b'Data in file.txt'},
    ]

    result = run(profile.name, 'python3 main.py', files=files)

    assert result['exit_code'] == 0
    assert result['stdout'] == b'Data in file.txt\n'


def test_start_sandbox_apierror_no_such_image():
    with pytest.raises(docker.errors.APIError) as excinfo:
        _start_sandbox('unknown_image', 'true', limits={'memory': 4})
    assert b'No such image' in excinfo.value.explanation


def test_working_directory():
    with working_directory() as workdir:
        assert os.stat(workdir).st_mode & 0o777 == 0o777
        assert os.listdir(workdir) == []
    assert not os.path.isdir(workdir)


def test_write_files():
    files = [
        {'name': 'main.py', 'content': b'main.py content'},
        {'name': 'file.txt', 'content': b'file.txt content'},
    ]

    with working_directory() as workdir:
        _write_files(files, workdir)

        assert set(os.listdir(workdir)) == {'main.py', 'file.txt'}
        mainpy_content = open(os.path.join(workdir, 'main.py'), 'rb').read()
        assert mainpy_content == b'main.py content'
        filetxt_content = open(os.path.join(workdir, 'file.txt'), 'rb').read()
        assert filetxt_content == b'file.txt content'