# VM commands

import click
from os import path, system

from azutil import enable_jit_access_on_vm, is_gpu, exec_script_using_ssh
from azutil import exec_command, jit_activate_vm, get_vm_size

@click.command()
@click.option("--vm-name", "-n", required=True, 
              help="Name of vm to create")
@click.option("--vm-size", "-s", 
              help="Size of Azure VM or '.' for local creation")
@click.option("--image", "-i", default="UbuntuLTS", 
              help="Image to use to create the VM (default UbuntuLTS)")
@click.option("--check-dns", "-c", is_flag=True, 
              help="Check if DNS name is available for --vm-name in region")
@click.pass_obj
def create(ez, vm_name, vm_size, image, check_dns):
    """Create a virtual machine"""

    # User can pass in nothing for --vm-size and we will helpfully list
    # all available vm sizes in the workspace region
    
    if vm_size == None:
        print(f"Missing VM size. VM sizes available in {ez.region}:")
        system((
            f"az vm list-sizes --subscription {ez.subscription} "
            f"--location {ez.region} --output table"))
        exit(1)

    # Check to see if the vm-name is taken already
    if check_dns:
        vm_dns_name = f"{vm_name}.{ez.region}.cloudapp.azure.com"
        if system(f"nslookup {vm_dns_name} > /dev/null") == 0:
            print((
                f"The domain name {vm_dns_name} is already taken. "
                f"Try a different --vm-name"))
            exit(1)

    # Select provisioning scripts for the VM based on whether vm_size is a GPU
    provision_vm_script = "provision-cpu"
    if is_gpu(vm_size):
        provision_vm_script = "provision-gpu"

    print((
        f"CREATING virtual machine {vm_name} size {vm_size} "
        f"in resource group {ez.resource_group}..."))
    az_vm_create = (
        f"az vm create --name {vm_name}"
        f"             --resource-group {ez.resource_group}"
        f"             --size {vm_size}"
        f"             --image {image}"
        f"             --ssh-key-values {ez.private_key_path}.pub"
        f"             --admin-username {ez.user_name}"
        f"             --public-ip-address-dns-name {vm_name}"
    )   
    exec_command(ez, az_vm_create)
    # TODO: analyze output for correct flags

    enable_jit_access_on_vm(ez, vm_name)

    print(f"INSTALLING system software on virtual machine")
    provision_vm_script_path = (
        f"{path.dirname(path.realpath(__file__))}/"
        f"{provision_vm_script}"
    )
    exec_script_using_ssh(ez, provision_vm_script_path, vm_name, "")
    ez.active_remote_vm = vm_name 
    exit(0)

@click.command()
def delete():
    """Delete a virtual machine"""
    pass

@click.command()
@click.pass_obj
def ls(ez):
    """List running virtual machines"""
    ls_cmd = (
        f"az vm list -d --resource-group {ez.resource_group} "
        f"--query=\"[?powerState=='VM running'].[name]\" -o tsv"
    )
    _, output = exec_command(ez, ls_cmd)

    print("RUNNNING VMs (* == current)")
    lines = output.splitlines()
    for line in lines:
        if line == ez.active_remote_vm:
            print(f"* {line}")
        else:
            print(f"  {line}")
    exit(0)

@click.command()
@click.option("--vm-name", "-n", help="Name of vm to start")
@click.pass_obj
def start(ez, vm_name):
    """Start a virtual machine"""
    vm_name = ez.get_active_vm_name(vm_name)
    jit_activate_vm(ez, vm_name)
    ez.active_remote_vm = vm_name
    exit(0)

@click.command()
@click.option("--vm-name", "-n", help="Name of vm to start")
@click.pass_obj
def stop(ez, vm_name):
    """Stop a virtual machine"""
    vm_name = ez.get_active_vm_name(vm_name)
    print(f"STOPPING virtual machine {vm_name}")
    exec_command(ez,
        f"az vm stop --name {vm_name} --resource-group {ez.resource_group}")
    exit(0)

@click.command()
@click.option("--vm-name", "-n", help="Name of vm to ssh into")
@click.pass_obj
def ssh(ez, vm_name):
    """SSH to a virtual machine"""
    vm_name = ez.get_active_vm_name(vm_name)
    jit_activate_vm(ez, vm_name)
    ssh_remote_host = (
        f"{ez.user_name}@{vm_name}."
        f"{ez.region}.cloudapp.azure.com"
    )
    ez.active_remote_vm = vm_name

    print(f"CONNECTING to {ssh_remote_host}")
    system((
        f"ssh -i {ez.private_key_path} "
        f" -o StrictHostKeyChecking=no "
        f"{ssh_remote_host}"
    ))

@click.command()
@click.option("--vm-name", "-n", help="Name of vm to ssh into")
@click.pass_obj
def select(ez, vm_name):
    """Select and optionally start a virtual machine"""
    vm_name = ez.get_active_vm_name(vm_name)
    _ = get_vm_size(ez, vm_name)

    # Just select the VM now
    print(f"SELECTING VM {vm_name}")
    ez.active_remote_vm = vm_name
    ez.active_remote_env = ""
    exit(0)

@click.command()
@click.option("--vm-name", "-n", help="Name of vm to ssh into")
@click.pass_obj
def info(ez, vm_name):
    """Get info about compute hardware"""
    vm_name = ez.get_active_vm_name(vm_name)
    vm_size = get_vm_size(ez, vm_name)

    # Now use the vm_size to get hardware details 
    _, details = exec_command(ez, 
        f"az vm list-sizes -l {ez.region} --output tsv | grep {vm_size}")
    specs = details.split("\t")
    print((
        f"VM INFO for {vm_name} size: {specs[2]}: "
        f"cores: {specs[3]} RAM: {specs[1]}MB Disk: {specs[5].strip()}MB"))
    exit(0)
