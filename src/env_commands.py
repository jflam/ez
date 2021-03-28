# env commands

import click
from azutil import exec_script_using_ssh, exit_on_error, is_gpu

@click.command()
@click.option("--env-name", "-n", required=True, help="Name of environment to start")
@click.option("--git-uri", "-g", required=True, help="URI of git repo to load in the environment")
@click.option("--user-interface", "-u", default="code", help="UI {notebook|lab|code} to use. Default is code")
@click.option("--vm-name", "-v", help="Name of the vm to use (default current active vm)")
@click.option("--git-clone", is_flag=True, help="Force fresh clone of source GitHub repo before starting environment")
@click.pass_obj
def run(ez, env_name, git_uri, user_interface, vm_name, git_clone):
    """Create and run an environment"""
    vm_name = ez.get_active_vm_name(vm_name)
    print(f"BUILDING {env_name} on {vm_name}...")

    # TODO: random number
    jupyter_port = 1235

    ez.debug_print(f"GET vm size for {vm_name}...")
    vm_size = ez.get_vm_size(vm_name)
    ez.debug_print(f"RESULT: {vm_size}")

    if is_gpu(vm_size):
        docker_gpu_flag = "--gpus all, --ipc=host"
        build_gpu_flag = "--gpu"
    else:
        docker_gpu_flag = ""
        build_gpu_flag = ""
    ez.debug_print(f"GPU flags: docker_gpu_flag {docker_gpu_flag} build_gpu_flag {build_gpu_flag}")

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
        f"--user-name {ez.user_name} "
    )
    ez.debug_print(f"BUILD command: {build_cmd}")

    ez.debug_print(f"EXECUTING build script on {vm_name}...")
    exit_code, output = exec_script_using_ssh(ez, "build", vm_name, build_cmd)
    exit_on_error(exit_code, output)
    ez.debug_print(f"DONE")

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