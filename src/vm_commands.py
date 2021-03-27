# VM commands

import click
from os import system

from azutil import is_gpu, exec_script_using_ssh, exec_command, login, jit_activate_vm, debug_print
from settings import ez_settings, get_active_vm_name, save_settings

@click.command()
@click.option("--vm-name", "-n", required=True, help="Name of vm to create")
@click.option("--vm-size", "-s", help="Size of Azure VM or '.' for local creation")
@click.option("--image", "-i", default="UbuntuLTS", help="Image to use to create the VM (default UbuntuLTS)")
@click.option("--check-dns", "-c", is_flag=True, help="Check if DNS name is available for --vm-name in region")
@click.option("--debug", is_flag=True, help="Output diagnostic information")
@click.option("--trace", is_flag=True, help="Trace execution")
def create(vm_name, vm_size, image, check_dns, debug, trace):
    """Create a virtual machine"""

    # User can pass in nothing for --vm-size and we will helpfully list
    # all available vm sizes in the workspace region
    region = ez_settings.region
    if vm_size == None:
        print(f"Missing VM size. VM sizes available in {region}:")
        system(f"az vm list-sizes --subscription {ez_settings.subscription} --location {region} --output table")
        exit(1)

    # Check to see if the vm-name is taken already
    if check_dns:
        vm_dns_name = f"{vm_name}.{region}.cloudapp.azure.com"
        if system(f"nslookup {vm_dns_name} > /dev/null") == 0:
            print(f"The domain name {vm_dns_name} is already taken. Try a different --vm-name")
            exit(1)

    # Select provisioning scripts for the VM based on whether vm_size is a GPU
    provision_vm_script = "provision-cpu"
    if is_gpu(vm_size):
        provision_vm_script = "provision-gpu"

    # TODO: enable JIT access when creating the virtual machine

    resource_group = f"{ez_settings.workspace_name}-rg"
    print(f"CREATING virtual machine {vm_name} size {vm_size} in resource group {resource_group}...")
    az_vm_create = (
        f"az vm create --name {vm_name}"
        f"             --resource-group {resource_group}"
        f"             --size {vm_size}"
        f"             --image {image}"
        f"             --ssh-key-values {ez_settings.private_key_path}.pub"
        f"             --admin-username {ez_settings.user_name}"
        f"             --public-ip-address-dns-name {vm_name}"
    )   
    exit_code, output = exec_command(az_vm_create, trace, debug)
    if exit_code != 0:
        exit(1)

    # TODO: analyze output for correct flags

    print(f"INSTALLING system software on virtual machine")
    exit_code, output = exec_script_using_ssh(provision_vm_script, vm_name, "", trace, debug)
    if exit_code != 0:
        exit(1)

    ez_settings.active_remote_vm = vm_name 
    save_settings(ez_settings)
    exit(0)

@click.command()
def delete():
    """Delete a virtual machine"""
    pass

@click.command()
def ls():
    """List running virtual machines"""
    pass

@click.command()
@click.option("--vm-name", "-n", help="Name of vm to start")
@click.option("--debug", is_flag=True, help="Output diagnostic information")
@click.option("--trace", is_flag=True, help="Trace execution")
def start(vm_name, debug, trace):
    """Start a virtual machine"""
    vm_name = get_active_vm_name(vm_name)
    login()
    jit_activate_vm(vm_name, debug, trace)
    ez_settings.active_remote_vm = vm_name
    save_settings(ez_settings)

@click.command()
def stop():
    """Stop a virtual machine"""
    pass

@click.command()
@click.option("--vm-name", "-n", help="Name of vm to ssh into")
@click.option("--debug", is_flag=True, help="Output diagnostic information")
@click.option("--trace", is_flag=True, help="Trace execution")
def ssh(vm_name, debug, trace):
    """SSH to a virtual machine"""
    vm_name = get_active_vm_name(vm_name)
    login()
    jit_activate_vm(vm_name, debug, trace)
    ssh_remote_host = (
        f"{ez_settings.user_name}@{vm_name}."
        f"{ez_settings.region}.cloudapp.azure.com"
    )
    ez_settings.active_remote_vm = vm_name
    save_settings(ez_settings)

    print(f"CONNECTING to {ssh_remote_host}")
    system((
        f"ssh -i {ez_settings.private_key_path} "
        f" -o StrictHostKeyChecking=no "
        f"{ssh_remote_host}"
    ))

@click.command()
def select():
    """Select and optionally start a virtual machine"""
    pass

@click.command()
def info():
    """Get info about compute hardware"""
    pass