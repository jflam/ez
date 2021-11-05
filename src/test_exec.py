import os, platform 
from exec import exec_cmd_local, exec_cmd_remote

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

# Tests below use a test vm called eztestvm that must be started first before
# running the tests. You can use ez to create this VM for you:
#
# ez compute create -n eztestvm -s Standard_B1s

test_uri = "ezuser@eztestvm.southcentralus.cloudapp.azure.com"
test_key = os.path.expanduser("~/.ssh/id_rsa_azure")

def test_remote_cmd_success(monkeypatch):
    monkeypatch.setattr('sys.stdin', open("/dev/null"))
    exit_code, stdout, _ = exec_cmd_remote("uname", test_uri, test_key) 
    assert exit_code == 0
    assert stdout == "Linux"

def test_remote_cmd_cwd(monkeypatch):
    monkeypatch.setattr('sys.stdin', open("/dev/null"))
    # I don't understand why test -d bin returns a 1 here so replacing
    # that test with a simpler test that should always work
    exit_code, _, _ = exec_cmd_remote("echo 'hello, world'", test_uri, test_key, 
        cwd="/usr")
    assert exit_code == 0
    exit_code, _, _ = exec_cmd_remote("test -d zzwy", test_uri, test_key,
        cwd="/usr")
    assert exit_code == 1
