import json

from ez_state import Ez, EzRuntime

def test_ez():
    """Test configuration of ez2 using dataclasses"""
    ez = Ez()
    ez.workspace_name = "bob"

    config = ez.__dict__
    assert config["workspace_name"] == "bob"

def test_load_ez():
    """Test serialization of ez2 using dataclasses"""
    with open("./test_data/southcentral.json", "rt") as f:
        config = json.load(f)

    ez = Ez(**config)
    assert ez.workspace_name == "ezws-eastus2"

    j = ez.__dict__
    assert j["workspace_name"] == "ezws-eastus2"

def test_empty_config():
    runtime = EzRuntime()
    assert runtime is not None

def test_config():
    runtime = EzRuntime("./test_data/.ez.json")
    assert runtime is not None
    assert runtime.config.current_workspace is not None
    keys = list(runtime.config.workspaces.keys())
    assert len(keys) == 2
    assert keys[0] == "ezws-westus2"
    assert keys[1] == "ezws-southcentralus"
    assert runtime.config.current_workspace == "ezws-westus2"
    assert runtime.config.workspaces["ezws-westus2"] is not None
    assert runtime.config.workspaces["ezws-southcentralus"] is not None
    ws1 = runtime.select("ezws-westus2")
    assert ws1 is not None
    assert ws1.workspace_name == "ezws-westus2"
    assert ws1.resource_group == "ez-workspace-rg"
    assert ws1.region == "westus2"
    ws2 = runtime.select("ezws-southcentralus")
    assert ws2 is not None
    assert ws2.workspace_name == "ezws-southcentralus"
    assert ws2.resource_group == "ezws-southcentral-rg"
    assert ws2.region == "southcentralus"

def test_switch_config():
    ez_config = EzRuntime("./test_data/.ez.json")
    with open("./test_data/southcentral.json", "rt") as f:
        new_config = json.load(f)
        
    new_ez_workspace = Ez(**new_config)
    assert new_ez_workspace.workspace_name == "ezws-eastus2"
    assert new_ez_workspace.region == "eastus2"
    assert new_ez_workspace.file_share_name == "ezdata"

    ez_config.add(new_ez_workspace)

    current_ws = ez_config.current()
    assert current_ws.workspace_name == "ezws-eastus2"
    assert current_ws.region == "eastus2"
    assert current_ws.file_share_name == "ezdata"

    westus2_ws = ez_config.select("ezws-westus2")
    assert westus2_ws.workspace_name == "ezws-westus2"
    assert westus2_ws.region == "westus2"
    assert westus2_ws.file_share_name == "ezdata"
    