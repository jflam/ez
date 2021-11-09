# Utility functions for working with Azure

import datetime
import json
import platform
import shlex

from exec import (exec_cmd_return_dataframe, exec_cmd, exec_file, 
    exit_on_error)
from getpass import getuser
from ez_state import Ez
from formatting import format_output_string, printf, printf_err
from os import path, system, makedirs, path, system
from rich import print
from rich.prompt import IntPrompt
from shutil import rmtree
from time import sleep

# Execute commands, either locally or remotely

def login(ez: Ez):
    """Login to Azure and GitHub using existing credentials"""

    # Daily check
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

def copy_to_clipboard(ez: Ez, text: str):
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

def get_active_compute_name(ez: Ez, compute_name) -> str:
    """Get the active compute name or exit. Passing None for compute_name
    returns the active remote compute, if it is set."""
    if compute_name == None:
        if ez.active_remote_compute == "":
            printf_err("No active remote compute: specify --compute-name")
            exit(1)
        else:
            return ez.active_remote_compute
    else:
        return compute_name

def get_compute_size(ez: Ez, compute_name) -> str:
    """Return the compute size of compute_name"""
    # Special return value for localhost
    if compute_name == '.':
        return '.'

    if ez.active_remote_compute_type == "k8s":
        # TODO: handle case where compute_type is AKS
        # For now, it always returns a GPU-enabled SKU
        return "Standard_NC6_Promo"
    elif ez.active_remote_compute_type == "vm":
        ez.debug_print(format_output_string(
            f"get compute size for {compute_name}"))
        get_compute_size_cmd = (
            f"az vm show --name {compute_name} "
            f"--resource-group {ez.resource_group} "
            f"--query hardwareProfile.vmSize -o tsv"
        )
        result = exec_cmd(get_compute_size_cmd)
        exit_on_error(result)
        compute_size = result.stdout
        ez.debug_print(format_output_string(f"result: {compute_size}"))
        return compute_size
    else:
        printf_err("Unknown active_remote_compute_type in ~/.ez.conf "
                   f"detected: {ez.active_remote_compute_type}")
        exit(1)

def is_vm_running(ez: Ez, vm_name) -> bool:
    is_running = (
        f"az vm list -d -o table --query "
        f"\"[?name=='{vm_name}'].{{PowerState:powerState}}\" | "
        f"grep \"VM running\" > /dev/null"
    )
    result = exec_cmd(is_running)
    return True if result.exit_code == 0 else False

def jit_activate_vm(ez: Ez, vm_name) -> None:
    """JIT activate vm_name for 3 hours"""
    # TODO: this is broken right now, they changed the resource ID
    # PolicyNotFound error coming back from the machine
    # while attempting this. This issue has some code that might
    # be helpful (though it seems to old to be helpful in this case)
    # https://github.com/Azure/azure-cli/issues/9855
    return
    if ez.disable_jit:
        return

    resource_group = f"{ez.workspace_name}-rg"

    print(f"CHECKING if virtual machine {vm_name} is running...")
    if not is_vm_running(ez, vm_name):
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

    ez.debug_print(f"GETTING local IP address...")
    get_my_ip_cmd = "curl -k -s https://ifconfig.me/ip"
    result = exec_cmd(get_my_ip_cmd)
    exit_on_error(result)
    local_ip_address = result.stdout
    ez.debug_print(f"RESULT: local IP address {local_ip_address}")

    ez.debug_print(f"GETTING virtual machine id for {vm_name}...")
    vm_show_cmd = (
        f"az vm show -n {vm_name} -g {resource_group} "
        f"-o tsv --query \"[id, location]\""
    )
    result = exec_cmd(vm_show_cmd)
    exit_on_error(result)
    vm_id, vm_location = result.stdout.splitlines()
    ez.debug_print(f"RESULT: virtual machine id {vm_id}")

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
    ez.debug_print(f"JIT ACTIVATE command: {jit_command}")

    # Make the REST API call using the az rest cli command

    ez.debug_print(f"REQUESTING JIT activation for {vm_name}...")
    result = exec_cmd(jit_command)
    exit_on_error(result)
    output = result.stdout
    ez.debug_print(f"RESULT {output}")

    # HACKHACK sleep for 3 seconds to allow enough time for JIT activate
    # to complete. Need to figure out how to wait on actual completion of
    # jit activation
    sleep(3) 
    print("JIT ACTIVATION COMPLETE")

    ez.jit_activated = True

def get_vm_size(ez: Ez, vm_name) -> str:
    """Return the VM size of vm_name"""
    vm_name = get_active_compute_name(ez, vm_name)
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

def generate_devcontainer_json(ez: Ez, jupyter_port_number, token, 
                               local=False, has_gpu=False):
    """Generate an appropriate devcontainer.json file"""
    if local:
        mount_config = (
            f'"mounts": ["source=/var/run/docker.sock,'
            f'target=/var/run/docker.sock,type=bind"],\n'
        )
        container_jupyter_dir = f"/workspaces/{ez.local_repo_name}/"
        container_jupyter_log = (
            f"/workspaces/{ez.local_repo_name}/jupyter.log")
        container_location = "localhost"
    else:
        mount_config = (
            f'"workspaceMount": "source=/home/{ez.user_name}'
            f'/easy/env/{ez.active_remote_env}/repo,target='
            f'/workspace,type=bind,consistency=cached"\n'
            f'"workspaceFolder": "/workspace",\n'
        )
        container_jupyter_dir = f"/workspaces/"
        container_jupyter_log = f"/workspaces/jupyter.log"
        container_location = (
            f"{ez.active_remote_compute}.{ez.region}.cloudapp.azure.com")
    
    if has_gpu:
        run_args = '"runArgs": ["--gpus=all", "--ipc=host"],'
    else:
        run_args = ""
    
    # Always run as interactive user when running locally?

    if local:
        ez.user_name = getuser()

    devcontainer_json = (
        f'{{\n'
        f'    "name": "on {container_location}",\n'
        # Note that this is tricky - the built container image name 
        # is the same as the environment name
        f'    "image": "{ez.active_remote_env}",\n'
        f'    "forwardPorts": [{jupyter_port_number}],\n'
        f'    {run_args}\n'
        f'    "containerUser": "{ez.user_name}",\n'
        f'    {mount_config}'
        f'    "settings": {{\n'
        f'        "terminal.integrated.shell.linux": "/bin/bash",\n'
        f'    }},\n'
        f'    "postStartCommand": "nohup jupyter notebook --no-browser '
        f'--port {jupyter_port_number} --ip=0.0.0.0 '
        f'--NotebookApp.token={token} --debug {container_jupyter_dir} '
        f'> {container_jupyter_log} 2>&1 &",\n'
        f'    "extensions": [\n'
        f'        "ms-python.python",\n'
        f'        "ms-toolsai.jupyter",\n'
        f'        "ms-python.vscode-pylance"\n'
        f'    ],\n'
        f'}}\n'
    )
    return devcontainer_json

def generate_settings_json(ez: Ez, is_local, jupyter_port_number, token):
    """Generate an appropriate settings.json file"""
    if not is_local:
        settings_json = (
            f'{{\n'
            f'    "docker.host": '
            f'"ssh://{ez.user_name}@{ez.active_remote_compute}.'
            f'{ez.region}.cloudapp.azure.com",\n'
            f'}}\n'
        )
    else:
        settings_json = (
            f'{{\n'
            f'    "python.dataScience.jupyterServerURI": "http://localhost:'
            f'{jupyter_port_number}/?token={token}",\n'
            # TODO: conditional for non native notebooks?
            f'    "jupyter.jupyterServerType": "remote",\n'
            f'}}\n'
        )

    return settings_json

def generate_remote_settings_json(ez: Ez, jupyter_port_number, token):
    """Generate remote_settings.json file"""
    remote_settings_json = (
        f'{{\n'
        f'    "python.dataScience.jupyterServerURI": '
        f'"http://localhost:{jupyter_port_number}/?token={token}"\n'
        f'}}\n'
    )
    return remote_settings_json

def build_container_image(ez: Ez, env_name, git_uri, jupyter_port, vm_name,
                          user_interface="code", force_git_clone=False, 
                          patch_file=None):
    """Build a container image either locally or remote"""
    git_clone_flag = "--git-clone" if force_git_clone else ""
    is_local = True if vm_name == "." else False

    # Generate command to launch build script
    build_script = "build_local" if is_local else "build"
    build_script_path = (
        f"{path.dirname(path.realpath(__file__))}/scripts/{build_script}")
    build_params = (
        f"--env-name {env_name} "
        f"--git-repo {git_uri} "
        f"--port {jupyter_port} "
        f"{git_clone_flag} "
        f"--user-interface {user_interface} "
        f"--user-name {ez.user_name} "
    )

    if patch_file is not None:
        build_params += f"--patch-file {patch_file} "

    # Execute script based on local vs remote case
    if not is_local:
        build_cmd = (
            f"cat > /tmp/build; chmod 755 /tmp/build; "
            f"/tmp/build {build_params}")
    else:
        build_cmd = f"{build_script_path} {build_params}"

    ez.debug_print(f"BUILD command: {build_cmd}")
    if is_local:
        print(f"BUILDING {env_name} on localhost ...")
    else:
        print(f"BUILDING {env_name} on {vm_name}...")

    if not is_local:
        ez.debug_print(f"EXECUTING build script on {vm_name}...")
        result = exec_file(build_script_path, 
            uri=get_compute_uri(ez, vm_name), 
            private_key_path=ez.private_key_path, 
            description=f"Executing build script on {vm_name}")
        exit_on_error(result)
    else:
        ez.debug_print(f"EXECUTING build script locally...")
        result = exec_cmd(build_cmd)
        exit_on_error(result)

    ez.debug_print(f"DONE")

# TODO: remove this method
def generate_vscode_project(ez: Ez, dir, git_uri, jupyter_port, token, 
                            vm_name, has_gpu, force_generate=False, 
                            is_k8s = False) -> str:
    """Generate a surrogate VS Code project at dir. Returns path to the 
    generated VS Code project."""
    is_local = True if vm_name == "." else False

    repo_name = path.basename(git_uri)
    if not is_local:
        local_dirname = f"{repo_name}_remote"
    else:
        local_dirname = repo_name

    path_to_vsc_project = f"{dir}/{local_dirname}"
    if path.exists(path_to_vsc_project) and force_generate:
        ez.debug_print(f"REMOVING existing directory: {path_to_vsc_project}")
        rmtree(path_to_vsc_project)

    print(f"CREATE surrogate VS Code project in {path_to_vsc_project}")

    # For local projects only, git clone into path_to_vsc_project
    if is_local:
        if not path.exists(path_to_vsc_project):
            print(f"CLONING {git_uri} into {path_to_vsc_project}...")
            result = exec_cmd(f"git clone {git_uri} {repo_name}")
            exit_on_error(result)
        else:
            print(
                f"SKIPPING git clone of {git_uri} as there is already a "
                f"{path_to_vsc_project} directory")

    # Do not generate .devcontainer for k8s
    if not is_k8s:
        if not path.exists(f"{path_to_vsc_project}/.devcontainer"):
            makedirs(f"{path_to_vsc_project}/.devcontainer")

    if not path.exists(f"{path_to_vsc_project}/.vscode"):
        makedirs(f"{path_to_vsc_project}/.vscode")

    if not is_k8s:
        devcontainer_path = (
            f"{path_to_vsc_project}/.devcontainer/devcontainer.json")
        devcontainer_json = generate_devcontainer_json(
            ez, jupyter_port, token, is_local, has_gpu
        )
        print(f"GENERATE devcontainer.json: {devcontainer_path}")
        with open(devcontainer_path, 'w') as file:
            file.write(devcontainer_json)

    settings_json_path = f"{path_to_vsc_project}/.vscode/settings.json"
    settings_json = generate_settings_json(ez, is_local, jupyter_port, token)

    print(f"GENERATE settings.json: {settings_json_path}")
    with open(settings_json_path, "w") as file:
        file.write(settings_json)

    if not is_local:
        remote_settings_json_path = (
            f"{path_to_vsc_project}/.vscode/remote_settings.json")
        remote_settings_json = generate_remote_settings_json(ez, 
                                                             jupyter_port, 
                                                             token)

        print(f"GENERATE remote_settings.json: {remote_settings_json_path}")
        with open(remote_settings_json_path, "w") as file:
            file.write(remote_settings_json)

        write_settings_json_cmd = (
            f'cat > /tmp/settings.json; mkdir -p /home/{ez.user_name}/'
            f'easy/env/{ez.active_remote_env}/repo/.vscode; '
            f'mv /tmp/settings.json /home/{ez.user_name}/'
            f'easy/env/{ez.active_remote_env}/repo/.vscode/settings.json'
        )
        # TODO: this isn't supported in exec_file today where we pipe in 
        # the contents of remote_settings_json_path into the ssh command
        # in write_settings_json_cmd on the remote machine
        # This doesn't matter because this method will be deprecated too
        # result = exec_file(remote_settings_json_path, 
        #     get_compute_uri(vm_name), private_key_path=)
        # exec_script_using_ssh(ez, remote_settings_json_path, 
        #                       vm_name, 
        #                       write_settings_json_cmd)
    
    return path_to_vsc_project

def launch_vscode(ez: Ez, dir):
    """Launch either VS Code or VS Code Insiders on dir"""

    # This is launched in Windows, not WSL 2, so I need to get the path to the
    # current WSL 2 directory from within WSL 2 The current WSL 2 distribution
    # is stored in the environment variable WSL_DISTRO_NAME

    # dir_path = path.expanduser(dir).replace('/', '\\')
    # wsl_distro_name = environ["WSL_DISTRO_NAME"]    
    # wsl_path = f"\\\\wsl$\\{wsl_distro_name}{dir_path}"
    # ez.debug_print(f"PATH: {wsl_path}")

    vscode_cmd = "code-insiders" if ez.insiders else "code"
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
    ez.debug_print(f"ENCODED path: {cmdline}")
    system(cmdline)

def install_local_dependencies():
    """Install local dependencies and validate they are there"""

    # install brew
    # install wget
    # install python/conda
    # install docker
    # install ruamel.yaml (via conda!)

def enable_jit_access_on_vm(ez: Ez, vm_name: str):
    return
    if ez.disable_jit:
        return 

    vm_show_cmd = (
        f"az vm show -n {vm_name} -g {ez.resource_group} "
        f"-o tsv --query \"[id, location]\""
    )
    result = exec_cmd(vm_show_cmd)
    exit_on_error(result)
    vm_id, vm_location = result.stdout.splitlines()
    ez.debug_print(f"RESULT: virtual machine id {vm_id}")

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
    ez.debug_print(f"JIT ENABLE command: {jit_command}")
    print(f"ENABLING JIT activation for {vm_name}...")
    result = exec_cmd(jit_command)
    exit_on_error(result)
    output = result.stdout
    ez.debug_print(f"RESULT {output}")

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

def mount_storage_account(ez: Ez, 
    compute_name: str, 
    mount_path: str, 
    persistent_mount: bool=False) -> bool:
    """Generate SMB path name for Azure File Share"""

    smb_path = (f"//{ez.storage_account_name}.file.core.windows.net/"
        f"{ez.file_share_name}")

    key = get_storage_account_key(ez.storage_account_name, ez.resource_group)

    # Ensure that the mount directory is created on the server
    cmd = f"mkdir -p {mount_path}"
    result = exec_cmd(cmd, get_compute_uri(ez, compute_name), 
        ez.private_key_path,
        description="creating data mount directory on remote compute")
    if result.exit_code != 0:
        printf_err(result.stderr)
        exit(result.exit_code)

    # Mount the Azure File Share onto the VM 
    # TODO: Add a flag that indicates whether we want to mount temporarily 
    # for the session or permanently via editing fstab
    # //servername/sharename  /media/windowsshare  cifs  guest,uid=1000,iocharset=utf8  0  0
    if persistent_mount:
        raise ValueError("persistent_mount True is not supported yet")

    cmd = f"sudo umount {mount_path}"
    result = exec_cmd(cmd, get_compute_uri(ez, compute_name), 
        ez.private_key_path,
        description="Dismounting Azure File share on remote compute")

    # File share may not be mounted so we don't exit here
    if result.exit_code != 0:
        printf_err(result.stderr)

    cmd = (f"sudo mount -t cifs {smb_path} {mount_path} "
        f"-o username={ez.storage_account_name},password={key},serverino,"
        f"uid={ez.user_name},file_mode=0777,dir_mode=0777")
    result = exec_cmd(cmd, get_compute_uri(ez, compute_name), 
        ez.private_key_path,
        description="Mounting Azure File share on remote compute")

    if result.exit_code != 0:
        printf_err(f"mount failed while running {cmd}")
        exit(result.exit_code)

    return result.exit_code == 0

def get_compute_uri(ez: Ez, compute_name: str) -> str:
    return f"{ez.user_name}@{compute_name}.{ez.region}.cloudapp.azure.com"
