# env commands

from os import chdir, getcwd, makedirs, mkdir, path, system
import click
from azutil import exec_script_using_ssh, exit_on_error, is_gpu
from azutil import generate_devcontainer_json, generate_remote_settings_json
from azutil import generate_settings_json

@click.command()
@click.option("--env-name", "-n", required=True, 
              help="Name of environment to start")
@click.option("--git-uri", "-g", required=True, 
              help="URI of git repo to load in the environment")
@click.option("--user-interface", "-u", default="code", 
              help="UI {notebook|lab|code} to use. Default is code")
@click.option("--vm-name", "-v", 
              help="Name of the vm to use (default current active vm)")
@click.option("--git-clone", is_flag=True, 
              help=(
                  "Force fresh clone of GitHub repo before "
                  "starting environment"))
@click.pass_obj
def run(ez, env_name, git_uri, user_interface, vm_name, git_clone):
    """Create and run an environment"""
    vm_name = ez.get_active_vm_name(vm_name)
    print(f"BUILDING {env_name} on {vm_name}...")

    # Initialize context
    ez.active_remote_vm = vm_name
    ez.active_remote_env = env_name

    # TODO: random numbers
    jupyter_port = 1235
    token="1234"

    if env_name == ".":
        is_local = True
    else:
        is_local = False

    ez.debug_print(f"GET vm size for {vm_name}...")
    vm_size = ez.get_vm_size(vm_name)
    ez.debug_print(f"RESULT: {vm_size}")

    has_gpu = is_gpu(vm_size)
    if has_gpu:
        docker_gpu_flag = "--gpus all, --ipc=host"
        build_gpu_flag = "--gpu"
    else:
        docker_gpu_flag = ""
        build_gpu_flag = ""
    ez.debug_print((
        f"GPU flags: docker_gpu_flag {docker_gpu_flag} "
        f"build_gpu_flag {build_gpu_flag}"))

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
    build_script_path = f"{path.dirname(path.realpath(__file__))}/scripts/build"
    exit_code, output = exec_script_using_ssh(ez, build_script_path, vm_name, build_cmd)
    exit_on_error(exit_code, output)
    ez.debug_print(f"DONE")

    repo_name = path.basename(git_uri)
    local_dirname = f"{repo_name}_remote"
    path_to_vsc_project = f"{getcwd()}/{local_dirname}"

    print(f"CREATE surrogate VS Code project in {path_to_vsc_project}")
    if not path.exists(f"{path_to_vsc_project}/.devcontainer"):
        makedirs(f"{path_to_vsc_project}/.devcontainer")
    if not path.exists(f"{path_to_vsc_project}/.vscode"):
        makedirs(f"{path_to_vsc_project}/.vscode")

    devcontainer_path = f"{path_to_vsc_project}/.devcontainer/devcontainer.json"
    devcontainer_json = generate_devcontainer_json(
        ez, jupyter_port, token, is_local, has_gpu
    )

    print(f"GENERATE {devcontainer_path}")
    with open(devcontainer_path, 'w') as file:
        file.write(devcontainer_json)

    settings_json_path = f"{path_to_vsc_project}/.vscode/settings.json"
    settings_json = generate_settings_json(ez)

    print(f"GENERATE {settings_json_path}")
    with open(settings_json_path, "w") as file:
        file.write(settings_json)

    remote_settings_json_path = (
        f"{path_to_vsc_project}/.vscode/remote_settings.json")
    remote_settings_json = generate_remote_settings_json(ez, jupyter_port, token)

    print(f"GENERATE {remote_settings_json_path}")
    with open(remote_settings_json_path, "w") as file:
        file.write(remote_settings_json)

    write_settings_json_cmd = (
        f'cat > /tmp/settings.json; mkdir -p /home/{ez.user_name}/'
        f'easy/env/{ez.active_remote_env}/repo/.vscode; '
        f'mv /tmp/settings.json /home/{ez.user_name}/'
        f'easy/env/{ez.active_remote_env}/repo/.vscode/settings.json'
    )
    exit_code, output = exec_script_using_ssh(ez, remote_settings_json_path, 
                                              vm_name, 
                                              write_settings_json_cmd)
    exit_on_error(exit_code, output)

    # TODO: add VS Code Insiders support
    print("LAUNCH Visual Studio Code")
    chdir(path_to_vsc_project)
    system("code .")
    exit(0)

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