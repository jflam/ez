import json

from ez_state import EzConfig, Ez

# Test configuration and multi-file configuration

def test_config():
    ez_config = EzConfig("./test_data/.ez.json")
    assert ez_config is not None
    config = ez_config.config    
    assert config is not None
    assert config["workspaces"] is not None
    assert config["current_workspace"] is not None
    keys = list(config["workspaces"].keys())
    assert len(keys) == 2
    assert keys[0] == "ezws-westus2"
    assert keys[1] == "ezws-southcentralus"
    assert config["current_workspace"] == "ezws-westus2"
    assert config["workspaces"]["ezws-westus2"] is not None
    assert config["workspaces"]["ezws-southcentralus"] is not None
    ws1 = ez_config.select("ezws-westus2")
    assert ws1 is not None
    assert ws1.workspace_name == "ezws-westus2"
    assert ws1.resource_group == "ez-workspace-rg"
    assert ws1.region == "westus2"
    ws2 = ez_config.select("ezws-southcentralus")
    assert ws2 is not None
    assert ws2.workspace_name == "ezws-southcentralus"
    assert ws2.resource_group == "ezws-southcentral-rg"
    assert ws2.region == "southcentralus"

def test_switch_config():
    ez_config = EzConfig("./test_data/.ez.json")
    with open("./test_data/southcentral.json", "rt") as f:
        new_config = json.load(f)
        
    new_ez_workspace = Ez(config_json=new_config)
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
    