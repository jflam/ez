# Utility functions for working with Azure

from os import system
from settings import ez_settings
import json
import shlex
import subprocess
import sys

def exec_script_using_ssh(ez, script_name, vm_name, cmd=""):
    """Execute script_name on vm_name"""
    if vm_name == None:
        vm_name = ez_settings.active_remote_vm
    cmd = shlex.quote(cmd)
    ssh_cmd = (
        f"cat scripts/{script_name} | "
        f"ssh -o StrictHostKeyChecking=no "
        f"-i {ez_settings.private_key_path} "
        f"{ez_settings.user_name}@{vm_name}.{ez_settings.region}.cloudapp.azure.com "
        f"{cmd}"
    )
    return exec_command(ez, ssh_cmd)

def exec_command(ez, command):
    """Shell execute command and capture output. Returns a tuple of (return
    value, output). If --trace set globally then just display commands but don't
    actually execute."""
    if not ez.logged_in:
        ez.logged_in = True 
        login()

    if ez.trace: 
        print(f"TRACE: {command}")
        return (0, "")
    else:
        try:
            # TODO: make this incremental char/line at a time
            output = subprocess.check_output(command, 
                                                stderr=subprocess.STDOUT, 
                                                shell=True).decode(sys.stdout.encoding)
            if ez.debug:
                print(f"DEBUG: {command}")
                print(f"OUTPUT: {output}")
            return (0, output)
        except subprocess.CalledProcessError as err:
            return (err.returncode, err.output.decode(sys.stdout.encoding))

def login():
    """Login using the interactive session user's credentials"""
    if system("az account show --query name > /dev/null") != 0:
        system("az login --use-device-code > /dev/null")

def is_gpu(vm_size):
    """Return true if vm_size is an Azure VM with a GPU"""
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
        f"az vm list -d -o table --query \"[?name=='{vm_name}'].{{PowerState:powerState}}\" | "
        f"grep \"VM running\" > /dev/null"
    )
    exit_code, _ = exec_command(ez, is_running)
    return True if exit_code == 0 else False

def exit_on_error(error_code, result):
    if error_code != 0:
        print(f"ERROR: {result}")
        exit(1)

def jit_activate_vm(ez, vm_name) -> None:
    """JIT activate vm_name for 3 hours"""
    resource_group = f"{ez_settings.workspace_name}-rg"

    print(f"CHECKING if virtual machine {vm_name} is running")
    if not is_vm_running(ez, vm_name):
        ez.debug_print(f"STARTING virtual machine {vm_name}")
        exec_command(ez, f"az vm start --name {vm_name} --resource-group {resource_group}")
        exec_command(ez, f"az vm wait --name {vm_name} --resource-group {resource_group} --updated")
    else:
        ez.debug_print(f"ALREADY RUNNING virtual machine {vm_name}")

    print(f"JIT ACTIVATING {vm_name}")

    # Get local machine IP address for JIT activation

    ez.debug_print(f"GETTING local IP address...")
    exit_code, local_ip_address = exec_command(ez, "curl -k -s https://ifconfig.me/ip")
    exit_on_error(exit_code, local_ip_address)
    ez.debug_print(f"RESULT: local IP address {local_ip_address}")

    ez.debug_print(f"GETTING virtual machine id for {vm_name}...")
    vm_show_cmd = (
        f"az vm show -n {vm_name} -g {resource_group} "
        f"-o tsv --query \"[id, location]\""
    )
    exit_code, results = exec_command(ez, vm_show_cmd)
    exit_on_error(exit_code, results)
    vm_id, vm_location = results.splitlines()
    ez.debug_print(f"RESULT: virtual machine id {vm_id}")

    subscription = ez_settings.subscription

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
    exit_code, output = exec_command(ez, jit_command)
    exit_on_error(exit_code, output)
    ez.debug_print(f"RESULT {output}")

def get_vm_size(ez, vm_name):
    """Return the VM size of vm_name"""
    vm_name = ez.get_active_vm_name(vm_name)
    info_cmd = (
        f"az vm get-instance-view --name {vm_name} --resource-group {ez.resource_group} "
        f"--query hardwareProfile.vmSize -o tsv"
    )
    exit_code, vm_size = exec_command(ez, info_cmd)
    exit_on_error(exit_code, vm_size)
    return vm_size
