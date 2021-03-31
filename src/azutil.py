# Utility functions for working with Azure

from os import path, system
import json
import shlex
import subprocess
import sys

def exec_script_using_ssh(ez, script_path, vm_name, cmd=""):
    """Execute script_name on vm_name.
    script_path must be an absolute path."""
    if vm_name == None:
        vm_name = ez.active_remote_vm
    cmd = shlex.quote(cmd)

    ssh_cmd = (
        f"cat {script_path} | "
        f"ssh -o StrictHostKeyChecking=no "
        f"-i {ez.private_key_path} "
        f"{ez.user_name}@{vm_name}.{ez.region}.cloudapp.azure.com "
        f"{cmd}"
    )
    return exec_command(ez, ssh_cmd)

def exec_command(ez, command, fail_fast=True):
    """Shell execute command and capture output. Returns a tuple of (return
    value, output). If --trace set globally then just display commands but
    don't actually execute."""
    if not ez.logged_in:
        ez.logged_in = True 
        login()

    if ez.trace: 
        print(f"TRACE: {command}")
        return (0, "")
    else:
        try:
            if ez.debug:
                print(f"DEBUG: {command}")
                print("OUTPUT: ")

            cumulative = ''
            process = subprocess.Popen(command,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT,
                                       shell=True)
            while True:
                output = process.stdout.read(1).decode(sys.stdout.encoding)
                cumulative += output

                if output == '' and process.poll() != None:
                    break

                if ez.debug:
                    sys.stdout.write(output)
                    sys.stdout.flush()

            return (process.returncode, cumulative.strip())
        except subprocess.CalledProcessError as err:
            error_message = err.output.decode(sys.stdout.encoding)
            if fail_fast:
                print(f"ERROR: {error_message}")
                exit(err.returncode)
            return (err.returncode, error_message)

def login():
    """Login using the interactive session user's credentials"""
    if system("az account show --query name > /dev/null") != 0:
        system("az login --use-device-code > /dev/null")

def is_gpu(vm_size):
    """Return true if vm_size is an Azure VM with a GPU"""

    # TODO: have local detection logic for GPU within WSL 2 (or mac)
    if vm_size == '.':
        return True     

    azure_gpu_sizes = [
        "Standard_NV6"
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
    return vm_size in azure_gpu_sizes

def is_vm_running(ez, vm_name) -> bool:
    is_running = (
        f"az vm list -d -o table --query "
        f"\"[?name=='{vm_name}'].{{PowerState:powerState}}\" | "
        f"grep \"VM running\" > /dev/null"
    )
    exit_code, _ = exec_command(ez, is_running, False)
    return True if exit_code == 0 else False

def jit_activate_vm(ez, vm_name) -> None:
    """JIT activate vm_name for 3 hours"""
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
        exec_command(ez, start_vm_cmd)
        exec_command(ez, wait_vm_cmd)
    else:
        print(f"ALREADY RUNNING virtual machine {vm_name}")

    print(f"JIT ACTIVATING {vm_name}...")

    # Get local machine IP address for JIT activation

    ez.debug_print(f"GETTING local IP address...")
    get_my_ip_cmd = "curl -k -s https://ifconfig.me/ip"
    _, local_ip_address = exec_command(ez, get_my_ip_cmd)
    ez.debug_print(f"RESULT: local IP address {local_ip_address}")

    ez.debug_print(f"GETTING virtual machine id for {vm_name}...")
    vm_show_cmd = (
        f"az vm show -n {vm_name} -g {resource_group} "
        f"-o tsv --query \"[id, location]\""
    )
    _, results = exec_command(ez, vm_show_cmd)
    vm_id, vm_location = results.splitlines()
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
    _, output = exec_command(ez, jit_command)
    ez.debug_print(f"RESULT {output}")
    print("JIT ACTIVATION COMPLETE")

def get_vm_size(ez, vm_name):
    """Return the VM size of vm_name"""
    vm_name = ez.get_active_vm_name(vm_name)
    info_cmd = (
        f"az vm get-instance-view --name {vm_name} "
        f"--resource-group {ez.resource_group} "
        f"--query hardwareProfile.vmSize -o tsv"
    )
    _, vm_size = exec_command(ez, info_cmd)
    return vm_size

def generate_devcontainer_json(ez, jupyter_port_number, token, 
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
            f"{ez.active_remote_vm}.{ez.region}.cloudapp.azure.com")
    
    if has_gpu:
        run_args = '"runArgs": ["--gpus=all", "--ipc=host"],'
    else:
        run_args = ""
    
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
        f'    "postStartCommand": "nohup jupyter notebook --no browser '
        f'--port {jupyter_port_number} --ip=0.0.0.0 --token={token} '
        f'--debug {container_jupyter_dir} > {container_jupyter_log} 2>&1 &",\n'
        f'    "extensions": [\n'
        f'        "ms-python.python",\n'
        f'        "ms-toolsai.jupyter",\n'
        f'        "ms-python.vscode-pylance"\n'
        f'    ],\n'
        f'}}\n'
    )
    return devcontainer_json

def generate_settings_json(ez, is_local, jupyter_port_number, token):
    """Generate an appropriate settings.json file"""
    if not is_local:
        settings_json = (
            f'{{\n'
            f'    "docker.host": "ssh://{ez.user_name}@{ez.active_remote_vm}.'
            f'{ez.region}.cloudapp.azure.com",\n'
            f'}}\n'
        )
    else:
        settings_json = (
            f'{{\n'
            f'    "python.dataScience.jupyterServerURI": "http://localhost:'
            f'{jupyter_port_number}/?token={token}",\n'
            f'}}\n'
        )

    return settings_json

def generate_remote_settings_json(ez, jupyter_port_number, token):
    """Generate remote_settings.json file"""
    remote_settings_json = (
        f'{{\n'
        f'    "python.dataScience.jupyterServerURI": '
        f'"http://localhost:{jupyter_port_number}/?token={token}"\n'
        f'}}\n'
    )
    return remote_settings_json