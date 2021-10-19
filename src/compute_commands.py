# Compute commands

import click
import json
import subprocess
from os import path, system

from azutil import enable_jit_access_on_vm, is_gpu, exec_script_using_ssh
from azutil import exec_command, jit_activate_vm, get_vm_size
from azutil import get_active_compute_name
from ez_state import Ez
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
@click.option("--no-install", "-q", is_flag=True, default=False,
              help=("Do not install system software"))
@click.pass_obj
def create(ez: Ez, compute_name, compute_size, compute_type, image, 
           check_dns, no_install):
    """Create a compute node"""

    # User can pass in nothing for --compute-size and we will helpfully list
    # all available vm sizes in the workspace region
    
    if compute_size == None:
        print(f"Missing VM size. VM sizes available in {ez.region}:")
        cmd = (f"az vm list-sizes --subscription {ez.subscription} "
               f"--location {ez.region} --output table")
        subprocess.run(cmd.split(" "))
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

        # TODO: parameterize this in .ez.conf
        os_disk_size = 256

        description = (
            f"[green]CREATING[/green] virtual machine {compute_name} size "
            f"{compute_size} in resource group {ez.resource_group}...")

        cmd = (
            f"az vm create --name {compute_name}"
            f"             --resource-group {ez.resource_group}"
            f"             --size {compute_size}"
            f"             --image {image}"
            f"             --ssh-key-values {ez.private_key_path}.pub"
            f"             --admin-username {ez.user_name}"
            f"             --public-ip-address-dns-name {compute_name}"
            f"             --public-ip-sku Standard"
            f"             --os-disk-size-gb {os_disk_size}"
        )   
        returncode, out = exec_command(ez, cmd, description=description)
        if returncode != 0:
            print(out)
            exit(1)
        
        if no_install:
            exit(0)

        # TODO: analyze output for correct flags
        enable_jit_access_on_vm(ez, compute_name)

        description = f"[green]INSTALLING[/green] system software on compute"
        provision_vm_script_path = (
            f"{path.dirname(path.realpath(__file__))}/scripts/"
            f"{provision_vm_script}"
        )
        exec_script_using_ssh(
            ez, 
            provision_vm_script_path, 
            compute_name, 
            description=description)

        # Now enable ssh on the remote machine
        # 1. generate key using ssh-keygen on remote machine
        # 2. copy public key back to this machine
        # 3. copy public key onto clipboard and open github and have
        #    instructions on how to define it

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

@click.option("--compute-name", "-c", required=True, 
              help="Name of compute to update")
@click.option("--compute-size", "-s", 
              help="Size of Azure VM or '.' for local update")
@click.command()
@click.pass_obj
def update_system(ez: Ez, compute_name, compute_size):
    """Update the system software on compute"""
    description = f"[green]UPDATING[/green] system software on compute"
    provision_vm_script = "provision-cpu"
    if is_gpu(compute_size):
        provision_vm_script = "provision-gpu"
    provision_vm_script_path = (
        f"{path.dirname(path.realpath(__file__))}/scripts/"
        f"{provision_vm_script}"
    )
    exec_script_using_ssh(
        ez, 
        provision_vm_script_path, 
        compute_name, 
        description=description,
        line_by_line=True)
    # Update current remote compute state
    ez.active_remote_compute = compute_name 
    ez.active_remote_compute_type = "vm"

@click.option("--compute-name", "-c", required=True, 
              help="Name of compute to update")
@click.command()
@click.pass_obj
def enable_acr(ez: Ez, compute_name: str):
    """Enable ACR on compute_name"""

    # Repository name maps to workspace name
    # Environment name maps to tag
    # e.g., jflamregistry.azurecr.io/ezws:pytorch_tutorials
    repository_name = ez.workspace_name

    # Note that az acr token create will recreate token if exists already
    cmd = (f"az acr token create --name {compute_name} "
           f"--registry {ez.registry_name} "
           f"--repository {repository_name} content/write content/read "
           f"--output json")
    fq_repo_name = f"{ez.registry_name}.azurecr.io/{repository_name}"
    result = exec_command(ez, 
                cmd, 
                log=True, 
                description=f"[green]GENERATING[/green] {fq_repo_name} token")

    # Get and save the JSON (for now so we don't need to create over and over)
    print(f"return code {result[0]}")
    output = result[1]
    print(output)
    j = json.loads(output)
    token_name = j["name"]
    password1 = j["credentials"]["passwords"][0]["value"]
    password2 = j["credentials"]["passwords"][1]["value"]
    print(password1)
    print(password2)

    # Generate the .bashrc that needs to existing on the server to assign
    # the token on each startup
    bashrc = f"""
docker login -u {token_name} -p {password1} {ez.registry_name}.azurecr.io
"""
    print(bashrc)

    # Check if the remote machine has a .bashrc and if it does, append
    # the bashrc script to that file
    # docker login -u MyToken -p pGTRFTc=thU7gu0PcnNoC8Dl8nzf1x9P jflamregistry.azurecr.io

    exit(0)

@click.command()
@click.option("--compute-name", "-c", help="Name of VM to delete")
@click.pass_obj
def delete(ez: Ez, compute_name):
    """Delete a compute node"""
    compute_name = get_active_compute_name(ez, compute_name)
    description = f"[green]DELETING[/green] compute node {compute_name}"
    exec_command(ez, (
        f"az vm delete --yes --name {compute_name} "
        f"--resource-group {ez.resource_group}"),
        description=description)
    exit(0)

@click.command()
@click.pass_obj
def ls(ez: Ez):
    """List running compute nodes"""
    ls_cmd = (
        f"az vm list -d --resource-group {ez.resource_group} "
        f"--query=\"[?powerState=='VM running'].[name]\" -o tsv"
    )
    description = f"[green]QUERYING[/green] Azure..."
    _, output = exec_command(ez, ls_cmd, description=description)

    # TODO cleanup output
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
@click.option("--compute-name", "-c", help="Name of VM to start")
@click.pass_obj
def start(ez: Ez, compute_name):
    """Start a virtual machine"""
    # TODO: do nothing if compute-name is not a VM
    compute_name = get_active_compute_name(ez, compute_name)
    jit_activate_vm(ez, compute_name)
    exec_command(ez, 
                 (f"az vm start --name {compute_name} "
                  f"--resource-group {ez.resource_group}"),
                 description=f"STARTING compute node {compute_name}")
    ez.active_remote_compute = compute_name
    exit(0)

@click.command()
@click.option("--compute-name", "-c", help="Name of VM to stop")
@click.pass_obj
def stop(ez: Ez, compute_name):
    """Stop a virtual machine"""
    compute_name = get_active_compute_name(ez, compute_name)
    # TODO: get compute_type too and fail for now on this
    exec_command(ez, 
                 (f"az vm deallocate --name {compute_name} "
                  f"--resource-group {ez.resource_group}"),
                 description=f"STOPPING compute node {compute_name}")
    exit(0)

@click.command()
@click.option("--compute-name", "-c", help="Name of VM to ssh into")
@click.pass_obj
def ssh(ez: Ez, compute_name):
    """SSH to a virtual machine"""
    compute_name = get_active_compute_name(ez, compute_name)
    # TODO: get compute_type too and fail for now on this
    jit_activate_vm(ez, compute_name)
    ez.active_remote_compute = compute_name
    ssh_remote_host = (
        f"{ez.user_name}@{compute_name}."
        f"{ez.region}.cloudapp.azure.com"
    )
    cmd = (
        f"ssh -i {ez.private_key_path} "
        f" -o StrictHostKeyChecking=no "
        f"{ssh_remote_host}"
    )
    print(f"[green]CONNECTING[/green] to {ssh_remote_host}")
    system(cmd)

@click.command()
@click.option("--compute-name", "-n", help="Name of compute node")
@click.option("--compute-type", "-t", default="vm",
              help=("Type of compute: vm (virtual machine) or "
              "k8s (Kubernetes)"))
@click.pass_obj
def select(ez: Ez, compute_name, compute_type):
    """Select a compute node"""
    compute_name = get_active_compute_name(ez, compute_name)

    # TODO: implement menu
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
def info(ez: Ez, compute_name):
    """Get info about compute hardware"""
    compute_name = get_active_compute_name(ez, compute_name)
    compute_size = get_vm_size(ez, compute_name)
    # TODO: do this with AKS and the correct compute pool

    # Now use the vm_size to get hardware details 
    description = f"[green]QUERYING[/green] {compute_name} for details..."
    retcode, out = exec_command(
        ez, 
        f"az vm list-sizes -l {ez.region} --output tsv | grep {compute_size}",
        description=description,
        debug=True)
    print(out)
    if retcode == 0:
        specs = out.split("\t")
        print((
            f"[green]INFO[/green] for {compute_name} size: {specs[2]}: "
            f"cores: {specs[3]} RAM: {specs[1]}MB Disk: {specs[5].strip()}MB"))
    else:
        print(f"[red]{out}[/red]")
    exit(retcode)
