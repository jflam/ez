# Test different commands in Azure
from exec import exec_cmd_return_dataframe, exec_cmd

# Replace these constants with resource groups that contain or do not contain
# an ACR
TEST_RESOURCE_GROUP_WITHOUT_ACR = "jflam-dask-experiments"
TEST_RESOURCE_GROUP_WITH_ACR = "ezws-southcentral-rg"

def test_read_empty_acr():
    cmd = (f"az acr list --resource-group {TEST_RESOURCE_GROUP_WITHOUT_ACR} "
            "-o tsv")
    df = exec_cmd_return_dataframe(cmd)
    assert df is None

def test_read_acr():
    cmd = (f"az acr list --resource-group {TEST_RESOURCE_GROUP_WITH_ACR} "
            "-o tsv")
    df = exec_cmd_return_dataframe(cmd)
    assert df is not None
    assert len(df.index) == 1
    registry_region = df.iloc[0][8]
    assert registry_region == "southcentralus"
