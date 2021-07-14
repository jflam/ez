# env commands

from os import getcwd, path
import click
from azutil import build_container_image, exec_command, launch_vscode
from azutil import generate_vscode_project, is_gpu, jit_activate_vm

def launch_user_interface(ez, user_interface, path_to_vscode_project, 
                          jupyter_port, token):
    """Bind user_interface to the running instance"""
    if user_interface == "code":
        print(f"LAUNCH vscode {path_to_vscode_project}")
        launch_vscode(ez, path_to_vscode_project)
    elif user_interface == "notebook" or user_interface == "lab":
        print(f"LAUNCH classic Jupyter "
              f"http://localhost:{jupyter_port}?token={token}")

def run_k8s(ez, env_name, git_uri, jupyter_port, compute_name,
            user_interface, git_clone, token, has_gpu, force_generate):
    """Run the environment in Kubernetes"""
    path_to_vscode_project = generate_vscode_project(ez, getcwd(), git_uri, 
                                                     jupyter_port, token, 
                                                     ".", has_gpu, 
                                                     force_generate, True)

    # ASSUME if path_to_vscode_project exists that image built alredy
    if not path.exists(path_to_vscode_project):
        build_cmd = (f"jupyter-repo2docker --image-name jflam/{env_name} "
                    f"--no-run {path_to_vscode_project}")
        print(f"BUILD Docker image locally: {build_cmd}")
        exec_command(ez, build_cmd)
        docker_cmd = (f"docker push jflam/{env_name}")
        print(f"PUSH Docker image to Docker Hub: {docker_cmd}")
        exec_command(ez, docker_cmd)

    launch_user_interface(ez, user_interface, path_to_vscode_project, 
                          jupyter_port, token)

    jupyter_variant = "notebook"
    if user_interface == "lab":
        jupyter_variant = "lab"

    kdo_cmd = (f"kdo -p {jupyter_port}:{jupyter_port} jflam/{env_name} "
               f"nohup jupyter {jupyter_variant} --no-browser "
               f"--port {jupyter_port} --ip=0.0.0.0 "
               f"--NotebookApp.token={token} .")

    # kdo blocks while syncing local filesystem into the pod
    # CTRL+C will terminate.
    print(f"START pod {kdo_cmd}")
    print("TERMINATE using CTRL+C")
    exec_command(ez, kdo_cmd)

def run_vm(ez, env_name, git_uri, jupyter_port, compute_name,
           user_interface, git_clone, token, has_gpu, force_generate):
    """Run the environment in a VM"""
    build_container_image(ez, env_name, git_uri, jupyter_port, compute_name,
                          user_interface, git_clone)
    path_to_vscode_project = generate_vscode_project(ez, getcwd(), git_uri, 
                                                     jupyter_port, token, 
                                                     compute_name, has_gpu, 
                                                     force_generate)

    launch_user_interface(ez, user_interface, path_to_vscode_project, 
                          jupyter_port, token)

@click.command()
@click.option("--env-name", "-n", required=True, 
              help="Name of environment to start")
@click.option("--git-uri", "-g", required=True, 
              help="URI of git repo to load in the environment")
@click.option("--user-interface", "-u", default="code", 
              help="UI {notebook|lab|code} to use. Default is code")
@click.option("--compute-name", "-c", 
              help=("compute node to use (default is the "
              "current active compute node)"))
@click.option("--git-clone", is_flag=True, 
              help=("Force fresh clone of GitHub repo before "
              "starting environment"))
@click.option("--force-generate", is_flag=True, default=False,
              help="Force generation of the local VS Code project")
@click.pass_obj
def run(ez, env_name, git_uri, user_interface, compute_name, git_clone, 
        force_generate):
    """Create and run an environment"""
    compute_name = ez.get_active_compute_name(compute_name)

    # Initialize context
    ez.active_remote_compute = compute_name
    ez.active_remote_env = env_name
    ez.local_repo_name = path.basename(git_uri)

    # TODO: random numbers
    jupyter_port = 1235
    token = "1234"

    compute_size = ez.get_compute_size(compute_name)
    has_gpu = is_gpu(compute_size)

    if ez.active_remote_compute_type == 'vm':
        run_vm(ez, env_name, git_uri, jupyter_port, compute_name,
               user_interface, git_clone, token, has_gpu, force_generate)
    elif ez.active_remote_compute_type == 'k8s':
        run_k8s(ez, env_name, git_uri, jupyter_port, compute_name,
                user_interface, git_clone, token, has_gpu, force_generate)
    else:
        print(f"Unknown active_remote_compute_type in ~/.ez.conf: "
            f"{ez.active_remote_compute_type}")
        exit(1)
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
@click.option("--compute-name", "-c", required=True,
              help="Compute name to migrate the environment to")
@click.option("--env-name", "-n", required=True,
              help="Environment name to start")
@click.pass_obj
def up(ez, compute_name, env_name):
    """Migrate the current environment to a new compute node"""

    # Let's assume that we are in a local environment for the purpose
    # of this. Later I will add heuristics to error out if this is not
    # the case.

    # Get the URI of the repo we are currently in
    _, git_remote_uri = exec_command(ez, 
        "git config --get remote.origin.url")

    if git_remote_uri == "":
        print(f"ERROR: directory {getcwd()} is not in a git repo")
        exit(1)

    print(f"MIGRATING {git_remote_uri} to {compute_name}")

    # Start the remote VM
    jit_activate_vm(ez, compute_name)
    ez.active_remote_compute = compute_name

    # Check to see if there are uncommitted changes
    patch_file = None
    exit_code, _ = exec_command(ez, 
        'git status | grep "Changes not staged for commit"', False)
    if exit_code == 0:
        print("STASHING uncommitted changes")
        exec_command(ez, "git stash")
        exec_command(ez, "git stash show -p --binary > ~/tmp/changes.patch")

        print(f"COPYING changes.patch to {compute_name}")
        scp_cmd = (
            f"scp -i {ez.private_key_path} "
            f"~/tmp/changes.patch "
            f"{ez.user_name}@{compute_name}.{ez.region}.cloudapp.azure.com:"
            f"/home/{ez.user_name}/tmp/changes.patch"
        )
        exec_command(ez, scp_cmd)
        patch_file = "changes.patch"

    print(f"STARTING {git_remote_uri} on {compute_name}")
    jupyter_port = 1235
    token = "1234"
    compute_size = ez.get_compute_size(compute_name)
    has_gpu = is_gpu(compute_size)
    build_container_image(ez, env_name, git_remote_uri, jupyter_port,
                          compute_name, "code", True, patch_file)
    path_to_vscode_project = generate_vscode_project(ez, getcwd(),
                                                     git_remote_uri,
                                                     jupyter_port, token,
                                                     compute_name, has_gpu, 
                                                     True)
    launch_vscode(ez, path_to_vscode_project)
    exit(0)
