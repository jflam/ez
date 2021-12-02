# Utility functions for working with Azure

import datetime
import getpass
import json
import platform
import re
import shlex
import urllib.parse

from exec import (exec_cmd_return_dataframe, exec_cmd, exit_on_error)
from ez_state import EzRuntime
from formatting import printf, printf_err
from os import path, system, path, system
from rich import print
from rich.prompt import IntPrompt
from time import sleep

# Execute commands, either locally or remotely

def login(runtime: EzRuntime):
    """Login to Azure and GitHub using existing credentials"""

    # Daily check
    ez = runtime.current()
    delta = datetime.datetime.now() - ez.last_auth_check
    if delta.days < 2:
        ez.logged_in = True
        return
    elif not ez.logged_in:
        if system("az account show --query name > /dev/null") != 0:
            success = system("az login --use-device-code > /dev/null")
            if success == 0:
                ez.logged_in = True
            else:
                printf_err("Could not log into Azure automatically. "
                    "Please login manually using: az login")
                exit(1)
        if system("gh auth status > /dev/null 2&>1") != 0:
            printf("start login procedure")
            success = system("gh auth login")
            if success == 0:
                ez.logged_in = True
            else:
                printf_err("Could not log into GitHub automatically. "
                    "Please login manually using: gh auth login")
                exit(1)

def copy_to_clipboard(runtime: EzRuntime, text: str):
    """Platform independent copy text to clipboard function"""
    if platform.system() == "Linux":
        if platform.release().find("WSL") != -1:
            clip = "clip.exe"
        else:
            print(f"Don't know what command to use for desktop linux")
            exit(1)
    elif platform.system() == "Darwin":
        clip = "pbcopy"

    cmd = f"echo \"{text}\" | {clip}"

    # Need to execute in a sub-shell
    system(cmd)

def is_gpu(vm_size):
    """Return true if vm_size is an Azure VM with a GPU"""

    # TODO: have local detection logic for GPU within WSL 2 (or mac)
    if vm_size == '.':
        return False     

    azure_gpu_sizes = [
        "Standard_NV6",
        "Standard_NV12",
        "Standard_NV24",
        "Standard_NV6_Promo",
        "Standard_NV12_Promo",
        "Standard_NV24_Promo",
        "Standard_NC6s_v3",
        "Standard_NC12s_v3",
        "Standard_NC24rs_v3",
        "Standard_NC24s_v3",
        "Standard_NC6",
        "Standard_NC12",
        "Standard_NC24",
        "Standard_NC24r",
        "Standard_NC6_Promo",
        "Standard_NC12_Promo",
        "Standard_NC24_Promo",
        "Standard_NC24r_Promo",
        "Standard_ND40rs_v2",
        "Standard_NV6s_v2",
        "Standard_NV12s_v2",
        "Standard_NV24s_v2",
        "Standard_NV12s_v3",
        "Standard_NV24s_v3",
        "Standard_NV48s_v3",
        "Standard_NC6s_v2",
        "Standard_NC12s_v2",
        "Standard_NC24rs_v2",
        "Standard_NC24s_v2",
        "Standard_NV4as_v4",
        "Standard_NV8as_v4",
        "Standard_NV16as_v4",
        "Standard_NV32as_v4"
    ]
    vm_size = vm_size.strip()
    result = vm_size in azure_gpu_sizes
    return result

def get_active_compute_name(runtime: EzRuntime, compute_name) -> str:
    """Get the active compute name or exit. Passing None for compute_name
    returns the active remote compute, if it is set."""
    ez = runtime.current()
    if compute_name == None:
        if ez.active_remote_compute == "":
            printf_err("No active remote compute: specify --compute-name")
            exit(1)
        else:
            return ez.active_remote_compute
    else:
        return compute_name

def is_vm_running(runtime: EzRuntime, vm_name) -> bool:
    is_running = (
        f"az vm list -d -o table --query "
        f"\"[?name=='{vm_name}'].{{PowerState:powerState}}\" | "
        f"grep \"VM running\" > /dev/null"
    )
    result = exec_cmd(is_running)
    return True if result.exit_code == 0 else False

def jit_activate_vm(runtime: EzRuntime, vm_name) -> None:
    """JIT activate vm_name for 3 hours"""
    # TODO: this is broken right now, they changed the resource ID
    # PolicyNotFound error coming back from the machine
    # while attempting this. This issue has some code that might
    # be helpful (though it seems to old to be helpful in this case)
    # https://github.com/Azure/azure-cli/issues/9855
    return
    ez = runtime.current()
    if ez.disable_jit:
        return

    resource_group = f"{ez.workspace_name}-rg"

    print(f"CHECKING if virtual machine {vm_name} is running...")
    if not is_vm_running(runtime, vm_name):
        print(f"STARTING virtual machine {vm_name}...")
        start_vm_cmd = (
            f"az vm start --name {vm_name} "
            f"--resource-group {resource_group}")
        wait_vm_cmd = (
            f"az vm wait --name {vm_name} "
            f"--resource-group {resource_group} --updated")
        result = exec_cmd(start_vm_cmd)
        exit_on_error(result)
        result = exec_cmd(wait_vm_cmd)
        exit_on_error(result)
    else:
        print(f"ALREADY RUNNING virtual machine {vm_name}")

    print(f"JIT ACTIVATING {vm_name}...")

    # Get local machine IP address for JIT activation

    runtime.debug_print(f"GETTING local IP address...")
    get_my_ip_cmd = "curl -k -s https://ifconfig.me/ip"
    result = exec_cmd(get_my_ip_cmd)
    exit_on_error(result)
    local_ip_address = result.stdout
    runtime.debug_print(f"RESULT: local IP address {local_ip_address}")

    runtime.debug_print(f"GETTING virtual machine id for {vm_name}...")
    vm_show_cmd = (
        f"az vm show -n {vm_name} -g {resource_group} "
        f"-o tsv --query \"[id, location]\""
    )
    result = exec_cmd(vm_show_cmd)
    exit_on_error(result)
    vm_id, vm_location = result.stdout.splitlines()
    runtime.debug_print(f"RESULT: virtual machine id {vm_id}")

    subscription = ez.subscription

    # Generate the URI of the JIT activate endpoint REST API

    endpoint = (
        f"https://management.azure.com/subscriptions/{subscription}/"
        f"resourceGroups/{resource_group}/providers/"
        f"Microsoft.Security/locations/{vm_location}/"
        f"jitNetworkAccessPolicies/default/initiate?api-version=2020-01-01"
    )

    # Generate the JSON body of REST call to endpoint

    body = {
        "virtualMachines": [
            {
                "id": vm_id,
                "ports": [
                    {
                        "number": 22,
                        "duration": "PT3H",
                        "allowedSourceAddressPrefix": local_ip_address
                    }
                ]
            }
        ],
        "justification": "ez JIT access"
    }
    body_json = shlex.quote(json.dumps(body))
    jit_command=f"az rest --method post --uri {endpoint} --body {body_json}"
    runtime.debug_print(f"JIT ACTIVATE command: {jit_command}")

    # Make the REST API call using the az rest cli command

    runtime.debug_print(f"REQUESTING JIT activation for {vm_name}...")
    result = exec_cmd(jit_command)
    exit_on_error(result)
    output = result.stdout
    runtime.debug_print(f"RESULT {output}")

    # HACKHACK sleep for 3 seconds to allow enough time for JIT activate
    # to complete. Need to figure out how to wait on actual completion of
    # jit activation
    sleep(3) 
    print("JIT ACTIVATION COMPLETE")

    ez.jit_activated = True

def get_vm_size(runtime: EzRuntime, vm_name) -> str:
    """Return the VM size of vm_name"""
    ez = runtime.current()
    vm_name = get_active_compute_name(runtime, vm_name)
    info_cmd = (
        f"az vm get-instance-view --name {vm_name} "
        f"--resource-group {ez.resource_group} "
        f"--query hardwareProfile.vmSize -o tsv"
    )
    result = exec_cmd(info_cmd, 
        description=f"Querying {vm_name} for its size")
    if result.exit_code == 0:
        return result.stdout
    else:
        return result.stderr

def launch_vscode(runtime: EzRuntime, dir):
    """Launch either VS Code or VS Code Insiders on dir"""

    # This is launched in Windows, not WSL 2, so I need to get the path to the
    # current WSL 2 directory from within WSL 2 The current WSL 2 distribution
    # is stored in the environment variable WSL_DISTRO_NAME

    # dir_path = path.expanduser(dir).replace('/', '\\')
    # wsl_distro_name = environ["WSL_DISTRO_NAME"]    
    # wsl_path = f"\\\\wsl$\\{wsl_distro_name}{dir_path}"
    # runtime.debug_print(f"PATH: {wsl_path}")

    ez = runtime.current()
    vscode_cmd = "code-insiders" if runtime.insiders else "code"
    # TODO: figure out a way to determine when Jupyter is started in the pod
    # because VS Code doesn't do a good job at retrying connection
    # TODO: this isn't working on remote containers right now
    # hex_dir_path = wsl_path.encode("utf-8").hex()
    # cmdline = (
    #     f"{vscode_cmd} --folder-uri "
    #     f"vscode-remote://dev-container+{hex_dir_path}/"
    #     f"workspaces/{ez.local_repo_name}")
    # Reverting to simpler form that forces the user to reopen in container
    # NOTE that this is opening from the WSL2 side not the Windows side
    # which is what the commented out code above tries (but fails) to do
    cmdline = f"{vscode_cmd} {path.expanduser(dir)}"
    runtime.debug_print(f"ENCODED path: {cmdline}")
    system(cmdline)

def enable_jit_access_on_vm(runtime: EzRuntime, vm_name: str):
    return
    ez = runtime.current()
    if ez.disable_jit:
        return 

    vm_show_cmd = (
        f"az vm show -n {vm_name} -g {ez.resource_group} "
        f"-o tsv --query \"[id, location]\""
    )
    result = exec_cmd(vm_show_cmd)
    exit_on_error(result)
    vm_id, vm_location = result.stdout.splitlines()
    runtime.debug_print(f"RESULT: virtual machine id {vm_id}")

    # Generate the URI of the JIT activate endpoint REST API

    endpoint = (
        f"https://management.azure.com/subscriptions/{ez.subscription}/"
        f"resourceGroups/{ez.resource_group}/providers/"
        f"Microsoft.Security/locations/{vm_location}/"
        f"jitNetworkAccessPolicies/default?api-version=2020-01-01"
    )

    # Generate the JSON body of REST call to endpoint

    body = {
        "kind": "Basic",
        "properties": {
            "virtualMachines": [
                {
                    "id": (
                        f"/subscriptions/{ez.subscription}"
                        f"/resourceGroups/{ez.resource_group}"
                        f"/providers/Microsoft.Compute"
                        f"/virtualMachines/{vm_name}"
                    ),
                    "ports": [
                        {
                            "number": 22,
                            "protocol": "*",
                            "allowedSourceAddressPrefix": "*",
                            "maxRequestAccessDuration": "PT3H"
                        }
                    ]
                }
            ],
            "provisioningState": "Succeeded",
        },
        "id": (
            f"/subscriptions/{ez.subscription}"
            f"/resourceGroups/{ez.resource_group}"
            f"/providers/Microsoft.Security"
            f"/locations/{vm_location}"
            f"/jitNetworkAccessPolicies/default"
        ),
        "name": "default",
        "type": "Microsoft.Security/locations/jitNetworkAccessPolicies",
        "location": vm_location
    }
    body_json = shlex.quote(json.dumps(body))
    jit_command=f"az rest --method post --uri {endpoint} --body {body_json}"
    runtime.debug_print(f"JIT ENABLE command: {jit_command}")
    print(f"ENABLING JIT activation for {vm_name}...")
    result = exec_cmd(jit_command)
    exit_on_error(result)
    output = result.stdout
    runtime.debug_print(f"RESULT {output}")

def pick_vm(resource_group, show_gpu_only=False):
    """Display a list of VMs from the resource group"""

    # Generate a dataframe that contains list of VMs in resource group
    # and whether each VM contains a GPU
    options = "Name:name, Size:hardwareProfile.vmSize, Running:powerState"
    cmd = (f"az vm list --resource-group {resource_group} --query "
           f"'[].{{{options}}}' -o tsv --show-details")
    df = exec_cmd_return_dataframe(cmd)
    df.columns = ["Name", "Size", "Running"]
    df["GPU"] = df["Size"].apply(lambda s: is_gpu(s))

    # Generate a list of options for the user to pick from reflecting
    # the show_gpu_only flag
    for i, row in df.iterrows():
        if show_gpu_only:
            if df["GPU"]:
                print(f"{i} {row['Name']} ({row['Running']})")
        else:
            print(f"{i} {row['Name']} ({row['Running']})")
    
    # Get input from user
    while True:
        choice = IntPrompt.ask("Enter VM # to use or -1 to create a new VM",
                               default=-1)
        if choice >= -1 and choice < df.shape[0]:
            break

    if choice == -1:
        print("TODO: implement create new VM option")
        exit(1)

    # Return the VM name to caller
    return df.iloc[choice]["Name"]

def get_storage_account_key(storage_account_name: str, 
    resource_group: str) -> str:
    """Retrieve storage account key for current account"""
    cmd = (f"az storage account keys list --resource-group "
        f"{resource_group} --account-name {storage_account_name} "
        f"--query \"[0].value\" --output json")
    
    result = exec_cmd(cmd, description="Retrieving storage account key")
    if result.exit_code == 0:
        return result.stdout.strip().strip('"')
    else:
        printf_err(result.stderr)
        exit(1)

def mount_storage_account(runtime: EzRuntime, 
    compute_name: str, 
    mount_path: str, 
    persistent_mount: bool=False) -> int:
    """Generate SMB path name for Azure File Share"""

    # Retrieve the storage account key and urlencode it
    ez = runtime.current()
    key = get_storage_account_key(ez.storage_account_name, ez.resource_group)
    quoted_key = urllib.parse.quote_plus(key)

    # Ensure that the mount directory is created on the server
    cmd = f"mkdir -p {mount_path}"
    if compute_name == ".":
        result = exec_cmd(cmd, 
        description="Creating local data mount directory")
    else:
        result = exec_cmd(cmd, get_compute_uri(runtime, compute_name), 
            ez.private_key_path,
            description="Creating remote data mount directory")
    exit_on_error(result)

    # Mount the Azure File Share onto the VM 
    # TODO: Add a flag that indicates whether we want to mount temporarily 
    # for the session or permanently via editing fstab
    # //servername/sharename  /media/windowsshare  cifs  guest,uid=1000,iocharset=utf8  0  0
    if persistent_mount:
        raise ValueError("persistent_mount True is not supported yet")

    if compute_name == ".":
        client_os = platform.system()
        if client_os == "Darwin":
            cmd = (f"mount_smbfs -d 0777 -f 0777 //{ez.storage_account_name}:"
                f"{quoted_key}@{ez.storage_account_name}."
                f"file.core.windows.net/{ez.file_share_name} {mount_path}")
        elif client_os == "Linux":
            cmd = (f"sudo mount -t cifs //{ez.storage_account_name}."
                f"file.core.windows.net/{ez.file_share_name} {mount_path} "
                f"-o username={ez.storage_account_name},password={key},"
                f"serverino,uid={getpass.getuser()},file_mode=0777,"
                f"dir_mode=0777")
        else:
            printf_err(f"Trying to mount on unsupported system {client_os}")
            exit(1)
        result = exec_cmd(cmd,
            description="Mounting local Azure File Share")
    else:
        cmd = (f"sudo mount -t cifs //{ez.storage_account_name}."
            f"file.core.windows.net/{ez.file_share_name} {mount_path} "
            f"-o username={ez.storage_account_name},password={key},serverino,"
            f"uid={ez.user_name},file_mode=0777,dir_mode=0777")
        result = exec_cmd(cmd, get_compute_uri(runtime, compute_name), 
            ez.private_key_path,
            description="Mounting remote Azure File Share")
    # exit_on_error(result)
    return result.exit_code

def get_compute_uri(runtime: EzRuntime, compute_name: str) -> str:
    ez = runtime.current()
    return f"{ez.user_name}@{compute_name}.{ez.region}.cloudapp.azure.com"

def get_host_ecdsa_key(runtime: EzRuntime, compute_name: str) -> str:
    ez = runtime.current()
    cmd = (f"az vm run-command invoke -g {ez.resource_group} "
        f"-n {compute_name} --command-id RunShellScript "
        f"--scripts 'cat /etc/ssh/ssh_host_ecdsa_key.pub' --output json")
    result = exec_cmd(cmd, 
        description=f"Retrieving ECDSA host key for {compute_name}")
    exit_on_error(result)
    j = json.loads(result.stdout)
    message = j["value"][0]["message"]
    key = re.findall(r'.*(ecdsa-sha2-nistp256\s.*?)\s.*', message)[0]
    return key
