# env commands

from os import chdir, getcwd, makedirs, path, system
import click
from azutil import build_container_image, exec_command, exec_script_using_ssh, launch_vscode
from azutil import generate_vscode_project, is_gpu
from azutil import generate_devcontainer_json, generate_remote_settings_json
from azutil import generate_settings_json, jit_activate_vm

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
@click.option("--force-generate", is_flag=True, default=False,
              help="Force generation of the local VS Code project")
@click.pass_obj
def run(ez, env_name, git_uri, user_interface, vm_name, git_clone, 
        force_generate):
    """Create and run an environment"""
    vm_name = ez.get_active_vm_name(vm_name)

    # Initialize context
    ez.active_remote_vm = vm_name
    ez.active_remote_env = env_name
    ez.local_repo_name = path.basename(git_uri)

    # TODO: refactor this into a build container image function in azutil.py
    # TODO: random numbers
    jupyter_port = 1235
    token = "1234"
    vm_size = ez.get_vm_size(vm_name)
    has_gpu = is_gpu(vm_size)

    build_container_image(ez, env_name, git_uri, jupyter_port, vm_name,
                          has_gpu, user_interface, git_clone)
    # if has_gpu:
    #     docker_gpu_flag = "--gpus all, --ipc=host"
    #     build_gpu_flag = "--gpu"
    # else:
    #     docker_gpu_flag = ""
    #     build_gpu_flag = ""
    # ez.debug_print((
    #     f"GPU flags: docker_gpu_flag {docker_gpu_flag} "
    #     f"build_gpu_flag {build_gpu_flag}"))

    # if git_clone:
    #     git_clone_flag = "--git-clone"
    # else:
    #     git_clone_flag = ""

    # # Generate command to launch build script
    # build_script_path = f"{path.dirname(path.realpath(__file__))}/scripts/build"
    # build_params = (
    #     f"--env-name {env_name} "
    #     f"--git-repo {git_uri} "
    #     f"--port {jupyter_port} "
    #     f"{git_clone_flag} "
    #     f"--user-interface {user_interface} "
    #     f"{build_gpu_flag} "
    #     f"--user-name {ez.user_name} "
    # )

    # # Execute script based on local vs remote case
    # if not is_local:
    #     build_cmd = f"cat > /tmp/build; chmod 755 /tmp/build; /tmp/build {build_params}"
    #     ez.debug_print(f"BUILD command: {build_cmd}")
    # else:
    #     build_cmd = f"{build_script_path} {build_params}"
    #     ez.debug_print(f"BUILD command: {build_cmd}")

    # ez.debug_print(f"BUILD command: {build_cmd}")
    # if not is_local:
    #     ez.debug_print(f"EXECUTING build script on {vm_name}...")
    #     exec_script_using_ssh(ez, build_script_path, vm_name, build_cmd)
    # else:
    #     ez.debug_print(f"EXECUTING build script locally...")
    #     exec_command(ez, build_cmd)

    # ez.debug_print(f"DONE")

    path_to_vscode_project = generate_vscode_project(ez, getcwd(), git_uri, 
                                                     jupyter_port, token, 
                                                     vm_name, has_gpu, 
                                                     force_generate)
    # repo_name = path.basename(git_uri)
    # if not is_local:
    #     local_dirname = f"{repo_name}_remote"
    # else:
    #     local_dirname = repo_name

    # path_to_vsc_project = f"{getcwd()}/{local_dirname}"

    # print(f"CREATE surrogate VS Code project in {path_to_vsc_project}")

    # # For local projects we git clone into path_to_vsc_project
    # if is_local:
    #     if not path.exists(path_to_vsc_project):
    #         print(f"CLONING {git_uri} into {path_to_vsc_project}...")
    #         exec_command(ez, f"git clone {git_uri} {repo_name}")
    #     else:
    #         print(f"SKIPPING git clone of {git_uri} as there is already {path_to_vsc_project} directory")

    # if not path.exists(f"{path_to_vsc_project}/.devcontainer"):
    #     makedirs(f"{path_to_vsc_project}/.devcontainer")
    # if not path.exists(f"{path_to_vsc_project}/.vscode"):
    #     makedirs(f"{path_to_vsc_project}/.vscode")

    # devcontainer_path = f"{path_to_vsc_project}/.devcontainer/devcontainer.json"
    # devcontainer_json = generate_devcontainer_json(
    #     ez, jupyter_port, token, is_local, has_gpu
    # )

    # print(f"GENERATE {devcontainer_path}")
    # with open(devcontainer_path, 'w') as file:
    #     file.write(devcontainer_json)

    # settings_json_path = f"{path_to_vsc_project}/.vscode/settings.json"
    # settings_json = generate_settings_json(ez, is_local, jupyter_port, token)

    # print(f"GENERATE {settings_json_path}")
    # with open(settings_json_path, "w") as file:
    #     file.write(settings_json)

    # if not is_local:
    #     remote_settings_json_path = (
    #         f"{path_to_vsc_project}/.vscode/remote_settings.json")
    #     remote_settings_json = generate_remote_settings_json(ez, jupyter_port, token)

    #     print(f"GENERATE {remote_settings_json_path}")
    #     with open(remote_settings_json_path, "w") as file:
    #         file.write(remote_settings_json)

    #     write_settings_json_cmd = (
    #         f'cat > /tmp/settings.json; mkdir -p /home/{ez.user_name}/'
    #         f'easy/env/{ez.active_remote_env}/repo/.vscode; '
    #         f'mv /tmp/settings.json /home/{ez.user_name}/'
    #         f'easy/env/{ez.active_remote_env}/repo/.vscode/settings.json'
    #     )
    #     exec_script_using_ssh(ez, remote_settings_json_path, 
    #                           vm_name, 
    #                           write_settings_json_cmd)

    launch_vscode(ez, path_to_vscode_project)
    # if ez.insiders:
    #     print("LAUNCH Visual Studio Code Insiders...")
    #     vscode_cmd = "code-insiders ."
    # else:
    #     print("LAUNCH Visual Studio Code")
    #     vscode_cmd = "code ."
    # chdir(path_to_vsc_project)
    # system(vscode_cmd)
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
@click.option("--vm-name", "-v", required=True,
              help="Name of the vm to migrate the environment to")
@click.option("--env-name", "-v", required=True,
              help="Name of environment to start")
@click.pass_obj
def up(ez, vm_name, env_name):
    """Migrate the current environment to a new VM"""

    # Let's assume that we are in a local environment for the purpose
    # of this. Later I will add heuristics to error out if this is not
    # the case.

    # Get the URI of the repo we are currently in
    _, git_remote_uri = exec_command(ez, 
        "git config --get remote.origin.url")

    if git_remote_uri == "":
        print(f"ERROR: directory {getcwd()} is not in a git repo")
        exit(1)

    print(f"MIGRATING {git_remote_uri} to {vm_name}")

    # Start the remote VM
    jit_activate_vm(ez, vm_name)
    ez.active_remote_vm = vm_name

    # Check to see if there are uncommitted changes
    patchfile_path = None
    exit_code, _ = exec_command(ez, 
        'git status | grep "Changes not staged for commit"', False)
    if exit_code == 0:
        print("STASHING uncommitted changes")
        exec_command(ez, "git stash")
        exec_command(ez, "git stash -p --binary > ~/tmp/changes.patch")

        print(f"COPYING changes.patch to {vm_name}")
        scp_cmd = (
            f"scp -i {ez.private_key_path} "
            f"~/tmp/changes.patch "
            f"{ez.user_name}@{vm_name}.{ez.region}.cloudapp.azure.com:"
            f"/home/{ez.user_name}/tmp/changes.patch"
        )
        exec_command(ez, scp_cmd)
        patchfile_path = path.expanduser("~/tmp/changes.patch")

    print(f"STARTING {git_remote_uri} on {vm_name}")
    jupyter_port = 1235
    token = "1234"
    vm_size = ez.get_vm_size(vm_name)
    has_gpu = is_gpu(vm_size)
    build_container_image(ez, env_name, git_remote_uri, jupyter_port,
                          vm_name, has_gpu, "code", True, patchfile_path)
    path_to_vscode_project = generate_vscode_project(ez, getcwd(),
                                                     git_remote_uri,
                                                     jupyter_port, token,
                                                     vm_name, has_gpu, True)
    launch_vscode(ez, path_to_vscode_project)
    exit(0)
