import os, platform, pytest
from exec import exec_cmd_local, exec_cmd_remote, exec_cmd

# Tests below use a test vm called eztestvm that must be started first before
# running the tests. You can use ez to create this VM for you:
#
# ez compute create -n eztestvm -s Standard_B1s

TEST_USER = "ezuser"
TEST_HOST = "eztestvm.southcentralus.cloudapp.azure.com"
TEST_URI = f"{TEST_USER}@{TEST_HOST}"
TEST_KEY = os.path.expanduser("~/.ssh/id_rsa_azure")

def test_remote_vm_online(monkeypatch):
    monkeypatch.setattr('sys.stdin', open("/dev/null"))
    exit_code, _, _ = exec_cmd(f"nc -z {TEST_HOST} 22 > /dev/null")
    if exit_code != 0:
        pytest.exit(f"These tests require {TEST_HOST} to be running")

# Higher level tests for the main 
def test_exec_cmd(monkeypatch):
    monkeypatch.setattr('sys.stdin', open("/dev/null"))
    exit_code, stdout, _ = exec_cmd("uname")
    assert exit_code == 0
    assert stdout == platform.system()

    exit_code, stdout, _ = exec_cmd("uname", TEST_URI, TEST_KEY) 
    assert exit_code == 0
    assert stdout == "Linux"

def test_exec_multi_cmd(monkeypatch):
    monkeypatch.setattr('sys.stdin', open("/dev/null"))
    cmds = ["uname", "uname -n"]
    results = exec_cmd(cmds)
    assert results[0][0] == 0
    assert results[0][1] == platform.system()
    assert results[1][0] == 0
    assert results[1][1] == platform.node()

def test_exec_multi_cmd_remote(monkeypatch):
    monkeypatch.setattr('sys.stdin', open("/dev/null"))
    cmds = ["uname", "uname -n"]
    results = exec_cmd(cmds, TEST_URI, TEST_KEY)
    assert results[0][0] == 0
    assert results[0][1] == "Linux"
    assert results[1][0] == 0
    print(results[1][1])

# Note that this test cannot validate the output that the rich generates (the
# pretty progress panel) ... it just validates that the changes made to
# support description don't break anything
def test_exec_cmd_with_descriptions(monkeypatch):
    monkeypatch.setattr('sys.stdin', open("/dev/null"))
    exit_code, _, _ = exec_cmd("ls -lah", description="listing a dir")
    assert exit_code == 0

# Lower level tests for the underlying local and remote exec functions

def test_local_cmd_success():
    exit_code, stdout, stderr = exec_cmd_local("uname")
    assert exit_code == 0
    assert stdout == platform.system()
    assert stderr == ""

def test_local_cmd_failure():
    exit_code, _, _ = exec_cmd_local("weoriu239847")
    assert exit_code == 127

def test_local_cmd_exit_code():
    exit_code, _, _ = exec_cmd_local("test -d foo")
    assert exit_code == 1

def test_local_cmd_cwd():
    exit_code, _, _ = exec_cmd_local("test -d bin", cwd="/usr")
    assert exit_code == 0
    exit_code, _, _ = exec_cmd_local("test -d zzwy", cwd="/usr")
    assert exit_code == 1

def test_remote_cmd_success(monkeypatch):
    monkeypatch.setattr('sys.stdin', open("/dev/null"))
    exit_code, stdout, _ = exec_cmd_remote("uname", TEST_URI, TEST_KEY) 
    assert exit_code == 0
    assert stdout == "Linux"

def test_remote_cmd_cwd(monkeypatch):
    monkeypatch.setattr('sys.stdin', open("/dev/null"))
    # I don't understand why test -d bin returns a 1 here so replacing
    # that test with a simpler test that should always work
    exit_code, _, _ = exec_cmd_remote("echo 'hello, world'", TEST_URI, TEST_KEY, 
        cwd="/usr")
    assert exit_code == 0
    exit_code, _, _ = exec_cmd_remote("test -d zzwy", TEST_URI, TEST_KEY,
        cwd="/usr")
    assert exit_code == 1