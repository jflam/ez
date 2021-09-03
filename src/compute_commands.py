# Compute commands

import click
from os import path, system

from azutil import enable_jit_access_on_vm, is_gpu, exec_script_using_ssh
from azutil import exec_command, jit_activate_vm, get_vm_size
from rich import print

@click.command()
@click.option("--compute-name", "-n", required=True, 
              help="Name of compute to create")
@click.option("--compute-size", "-s", 
              help="Size of Azure VM or '.' for local creation")
@click.option("--compute-type", "-t", default="vm",
              help=("Type of compute: vm (virtual machine) or "
              "k8s (Kubernetes)"))
@click.option("--image", "-i", default="UbuntuLTS", 
              help="Image to use to create the VM (default UbuntuLTS)")
@click.option("--check-dns", "-c", is_flag=True, 
              help=("Check if DNS name is available for "
              "--compute-name in region"))
@click.pass_obj
def create(ez, compute_name, compute_size, compute_type, image, check_dns):
    """Create a compute node"""

    # User can pass in nothing for --compute-size and we will helpfully list
    # all available vm sizes in the workspace region
    
    if compute_size == None:
        print(f"Missing VM size. VM sizes available in {ez.region}:")
        system((
            f"az vm list-sizes --subscription {ez.subscription} "
            f"--location {ez.region} --output table"))
        exit(1)

    # Check to see if the compute-name is taken already
    if check_dns:
        compute_dns_name = f"{compute_name}.{ez.region}.cloudapp.azure.com"
        if system(f"nslookup {compute_dns_name} > /dev/null") == 0:
            print((
                f"The domain name {compute_dns_name} is already taken. "
                f"Try a different --compute-name"))
            exit(1)

    # Select provisioning scripts for the VM based on whether compute_size is
    # a GPU
    if compute_type == "vm":
        provision_vm_script = "provision-cpu"
        if is_gpu(compute_size):
            provision_vm_script = "provision-gpu"

        print((
            f"CREATING virtual machine {compute_name} size {compute_size} "
            f"in resource group {ez.resource_group}..."))
        az_vm_create = (
            f"az vm create --name {compute_name}"
            f"             --resource-group {ez.resource_group}"
            f"             --size {compute_size}"
            f"             --image {image}"
            f"             --ssh-key-values {ez.private_key_path}.pub"
            f"             --admin-username {ez.user_name}"
            f"             --public-ip-address-dns-name {compute_name}"
        )   
        exec_command(ez, az_vm_create)
        # TODO: analyze output for correct flags

        if not ez.disable_jit:
            enable_jit_access_on_vm(ez, compute_name)

        print(f"INSTALLING system software on virtual machine")
        provision_vm_script_path = (
            f"{path.dirname(path.realpath(__file__))}/scripts/"
            f"{provision_vm_script}"
        )
        exec_script_using_ssh(ez, provision_vm_script_path, compute_name, "")
        ez.active_remote_compute = compute_name 
        ez.active_remote_compute_type = compute_type
        exit(0)
    elif compute_type == "k8s":
        # TODO: implement
        print(f"NOT IMPLEMENTED create --compute-type=k8s. Manually create.")
        exit(1)
    else:
        print(f"Unknown --compute-type: {compute_type}")
        exit(1)

@click.command()
def delete():
    """Delete a compute node"""
    pass

@click.command()
@click.pass_obj
def ls(ez):
    """List running compute nodes"""
    ls_cmd = (
        f"az vm list -d --resource-group {ez.resource_group} "
        f"--query=\"[?powerState=='VM running'].[name]\" -o tsv"
    )
    _, output = exec_command(ez, ls_cmd)

    print("RUNNING VMs (* == current)")
    lines = output.splitlines()
    for line in lines:
        if line == ez.active_remote_compute:
            print(f"* [green]{line}[/green]")
        else:
            print(f"  {line}")

    print("RUNNING AKS clusters (* == current)")
    print("TODO")
    exit(0)

@click.command()
@click.option("--compute-name", "-n", help="Name of VM to start")
@click.pass_obj
def start(ez, compute_name):
    """Start a virtual machine"""
    # TODO: do nothing if compute-name is not a VM
    compute_name = ez.get_active_compute_name(compute_name)
    jit_activate_vm(ez, compute_name)
    ez.active_remote_compute = compute_name
    exit(0)

@click.command()
@click.option("--compute-name", "-n", help="Name of VM to start")
@click.pass_obj
def stop(ez, compute_name):
    """Stop a virtual machine"""
    compute_name = ez.get_active_compute_name(compute_name)
    # TODO: get compute_type too and fail for now on this
    print(f"STOPPING compute node {compute_name}")
    exec_command(ez, (
        f"az vm stop --name {compute_name} "
        f"--resource-group {ez.resource_group}"))
    exit(0)

@click.command()
@click.option("--compute-name", "-n", help="Name of VM to ssh into")
@click.pass_obj
def ssh(ez, compute_name):
    """SSH to a virtual machine"""
    compute_name = ez.get_active_compute_name(compute_name)
    # TODO: get compute_type too and fail for now on this
    jit_activate_vm(ez, compute_name)
    ssh_remote_host = (
        f"{ez.user_name}@{compute_name}."
        f"{ez.region}.cloudapp.azure.com"
    )
    ez.active_remote_compute = compute_name

    print(f"CONNECTING to {ssh_remote_host}")
    system((
        f"ssh -i {ez.private_key_path} "
        f" -o StrictHostKeyChecking=no "
        f"{ssh_remote_host}"
    ))

@click.command()
@click.option("--compute-name", "-n", help="Name of compute node")
@click.option("--compute-type", "-t", default="vm",
              help=("Type of compute: vm (virtual machine) or "
              "k8s (Kubernetes)"))
@click.pass_obj
def select(ez, compute_name, compute_type):
    """Select a compute node"""
    compute_name = ez.get_active_compute_name(compute_name)

    if compute_type == "vm":
        _ = get_vm_size(ez, compute_name)

        # Just select the compute node now
        print(f"SELECTING VM {compute_name}")
        ez.active_remote_compute = compute_name
        ez.active_remote_compute_type = compute_type
        ez.active_remote_env = ""
        exit(0)
    elif compute_type == "k8s":
        exec_command(ez, f"kubectl config use-context {compute_name}")
        ez.active_remote_compute = compute_name
        ez.active_remote_compute_type = compute_type
        ez.active_remote_env = ""
        exit(0)

@click.command()
@click.option("--compute-name", "-n", help="Name of compute node")
@click.pass_obj
def info(ez, compute_name):
    """Get info about compute hardware"""
    compute_name = ez.get_active_compute_name(compute_name)
    compute_size = get_vm_size(ez, compute_name)
    # TODO: do this with AKS and the correct compute pool

    # Now use the vm_size to get hardware details 
    _, details = exec_command(ez, 
        f"az vm list-sizes -l {ez.region} --output tsv | grep {compute_size}")
    specs = details.split("\t")
    print((
        f"VM INFO for {compute_name} size: {specs[2]}: "
        f"cores: {specs[3]} RAM: {specs[1]}MB Disk: {specs[5].strip()}MB"))
    exit(0)
