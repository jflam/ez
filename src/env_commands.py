# env commands

import click
from azutil import debug_print, exec_script_using_ssh, exit_on_error, get_vm_size, jit_activate_vm, is_gpu
from settings import ez_settings, get_active_vm_name

@click.command()
@click.option("--env-name", "-n", required=True, help="Name of environment to start")
@click.option("--git-uri", "-g", required=True, help="URI of git repo to load in the environment")
@click.option("--user-interface", "-u", default="code", help="UI {notebook|lab|code} to use. Default is code")
@click.option("--vm-name", "-v", help="Name of the vm to use (default current active vm)")
@click.option("--git-clone", is_flag=True, help="Force fresh clone of source GitHub repo before starting environment")
@click.option("--debug", is_flag=True, help="Output diagnostic information")
@click.option("--trace", is_flag=True, help="Trace execution")
def run(env_name, git_uri, user_interface, vm_name, git_clone, debug, trace):
    """Create and run an environment"""
    resource_group = f"{ez_settings.workspace_name}-rg"
    vm_name = get_active_vm_name(vm_name)
    print(f"BUILDING {env_name} on {vm_name}...")

    # TODO: random number
    jupyter_port = 1235

    debug_print(f"GET vm size for {vm_name}...", debug)
    vm_size = get_vm_size(vm_name)
    debug_print(f"RESULT: {vm_size}", debug)

    if is_gpu(vm_size):
        docker_gpu_flag = "--gpus all, --ipc=host"
        build_gpu_flag = "--gpu"
    else:
        docker_gpu_flag = ""
        build_gpu_flag = ""
    debug_print(f"GPU flags: docker_gpu_flag {docker_gpu_flag} build_gpu_flag {build_gpu_flag}", debug)

    if git_clone:
        git_clone_flag = "--git-clone"
    else:
        git_clone_flag = ""

    # Generate command to launch build script
    build_cmd = (
        f"cat > /tmp/build ; chmod 755 /tmp/build ; "
        f"/tmp/build --env-name {env_name} "
        f"--git-repo {git_uri} "
        f"--port {jupyter_port} "
        f"{git_clone_flag} "
        f"--user-interface {user_interface} "
        f"{build_gpu_flag} "
        f"--user-name {ez_settings.user_name} "
    )
    debug_print(f"BUILD command: {build_cmd}", debug)

    debug_print(f"EXECUTING build script on {vm_name}...", debug)
    exit_code, output = exec_script_using_ssh("build", vm_name, build_cmd, debug, trace)
    exit_on_error(exit_code, output)
    debug_print(f"DONE", debug)
    

@click.command()
def ls():
    """List running environments"""
    pass

@click.command()
def cp():
    """Copy local files to/from an environment"""
    pass

@click.command()
def ssh():
    """SSH to an environment"""
    pass

@click.command()
def stop():
    """Stop an environment"""
    pass

@click.command()
def up():
    """Migrate the current environment to a new VM"""
    pass