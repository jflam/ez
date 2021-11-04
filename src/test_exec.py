import io
import platform 
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

def test_remote_cmd_success(monkeypatch):
    monkeypatch.setattr('sys.stdin', open("/dev/null"))
    exit_code, stdout, _ = exec_cmd_remote("uname", 
        "ezuser@eztestvm.southcentralus.cloudapp.azure.com",
        "/Users/jlam/.ssh/id_rsa_azure")
    assert exit_code == 0
    assert stdout == "Linux"
