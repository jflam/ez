# env commands

import click, json, os, random, subprocess, uuid

from azutil import build_container_image, exec_command, launch_vscode, pick_vm
from azutil import generate_vscode_project, is_gpu, jit_activate_vm
from azutil import get_active_compute_name, get_compute_size
from ez_state import Ez
from os import getcwd, path

def launch_user_interface(ez: Ez, user_interface, path_to_vscode_project, 
                          jupyter_port, token):
    """Bind user_interface to the running instance"""
    if user_interface == "code":
        print(f"LAUNCH vscode {path_to_vscode_project}")
        launch_vscode(ez, path_to_vscode_project)
    elif user_interface == "notebook" or user_interface == "lab":
        print(f"LAUNCH classic Jupyter "
              f"http://localhost:{jupyter_port}?token={token}")

def run_k8s(ez: Ez, env_name, git_uri, jupyter_port, compute_name,
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

    kdo_cmd = (f"kdo -p {jupyter_port}:{jupyter_port} "
               "--spec '{\"resources\":{\"limits\":{\"nvidia.com/gpu\":\"1\"}}}' "
               f"jflam/{env_name} "
               f"nohup jupyter {jupyter_variant} --no-browser "
               f"--port {jupyter_port} --ip=0.0.0.0 "
               f"--NotebookApp.token={token} .")

    # kdo blocks while syncing local filesystem into the pod
    # CTRL+C will terminate.
    print(f"START pod {kdo_cmd}")
    print("TERMINATE using CTRL+C")
    exec_command(ez, kdo_cmd)

def run_vm(ez: Ez, env_name, git_uri, jupyter_port, compute_name,
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
def run(ez: Ez, env_name, git_uri, user_interface, compute_name, git_clone, 
        force_generate):
    """Create and run an environment"""
    compute_name = get_active_compute_name(ez, compute_name)

    # Initialize context
    ez.active_remote_compute = compute_name
    ez.active_remote_env = env_name
    ez.local_repo_name = path.basename(git_uri)

    jupyter_port = random.randint(1024, 8192)
    token = uuid.uuid4().hex 

    compute_size = get_compute_size(ez, compute_name)
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
@click.pass_obj
def ls(ez: Ez):
    """List running environments"""
    pass

@click.command()
@click.argument("src")
@click.argument("dest")
@click.pass_obj
def cp(ez: Ez, src, dest):
    """
Copy local files to/from an environment.

ez env cp <source> <dest>

The format of <source> and <dest> are important. Examples:

\b
foo.txt :.               Copy foo.txt to active environment /workspace dir
foo.txt :/remote/path    Copy foo.txt to active environment
:/remote/path/foo.txt .  Copy active environment foo.txt locally
./*.txt :/remote/path    Copy local .txt files to active environment
:/remote/path/*.txt ./   Copy active environment .txt files locally
    """
    if not ez.active_remote_env:
        print("No running environment.")
        exit(1)
    
    if not src:
        print("Missing src argument")
        exit(1)
    
    if not dest:
        print("Missing dest argument")
        exit(1)
    
    if src.startswith(":") and dest.startswith(":"):
        print("Both src and dest cannot start with ':' to indicate remote")
        exit(1)
    elif src.startswith(":"):
        cmd = (f"scp -i {ez.private_key_path} {ez.user_name}@"
               f"{ez.active_remote_compute}.{ez.region}"
               f".cloudapp.azure.com:/home/{ez.user_name}/src/"
               f"{ez.active_remote_env}/{src[1:]} {dest}") 
        subprocess.run(cmd.split(" "))
    elif dest.startswith(":"):
        cmd = (f"scp -i {ez.private_key_path} {src} {ez.user_name}@"
               f"{ez.active_remote_compute}.{ez.region}"
               f".cloudapp.azure.com:/home/{ez.user_name}/src/"
               f"{ez.active_remote_env}/{dest[1:]}") 
        subprocess.run(cmd.split(" "))
    else:
        print("One of src or dest must start with ':' to indicate remote")
        exit(1)

@click.command()
@click.option("--compute-name", "-c", required=False,
              help="Compute name to migrate the environment to")
@click.option("--env-name", "-n", required=False,
              help="Environment name to start")
@click.pass_obj
def ssh(ez: Ez, compute_name, env_name):
    """SSH to an environment"""
    if not ez.active_remote_compute:
        if not compute_name:
            print("--compute-name parameter must be specified because there "
                  "isn't an active compute environment.")
            exit(1)
    else:
        compute_name = ez.active_remote_compute

    if not ez.active_remote_env:
        if not env_name:
            print("--env-name parameter must be specified because there "
                  "isn't an active environment.")    
            exit(1)
    else:
        env_name = ez.active_remote_env

    # Run docker ps on the remote VM to figure out what the container id of 
    # the running VS Code container is
    cmd = (f"ssh -i {ez.private_key_path} {ez.user_name}@{compute_name}."
           f"{ez.region}.cloudapp.azure.com docker ps --format "
           "{{.Image}},{{.ID}}")
    result = subprocess.run(cmd.split(' '), capture_output=True)
    containers = result.stdout.decode("utf-8").split("\n")
    active_container_name = f"vsc-{env_name}-"
    vsc_containers = [c for c in containers if c.startswith(active_container_name)]
    if len(vsc_containers) != 1:
        print(f"ERROR: >1 container running with same env_name:")
        print(vsc_containers)
        exit(1)

    # Open a tunneled SSH connection into the running remote container
    image_name, container_id = vsc_containers[0].split(",")
    cmd = (f"ssh -tt -i {ez.private_key_path} {ez.user_name}@{compute_name}."
           f"{ez.region}.cloudapp.azure.com docker exec -it "
           f"-w /workspace {container_id} /bin/bash")
    print(f"SSH connection to container {container_id} running using image "
          f"{image_name} on {compute_name}.{ez.region}.cloudapp.azure.com")
    subprocess.run(cmd.split(' '))

@click.command()
@click.pass_obj
def stop(ez: Ez):
    pass

@click.command()
@click.option("--compute-name", "-c", required=False,
              help="Compute name to migrate the environment to")
@click.option("--env-name", "-n", required=False,
              help="Environment name to start")
@click.pass_obj
def up(ez: Ez, compute_name, env_name):
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
    compute_size = get_compute_size(ez, compute_name)
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

def exec_subprocess(cmd: str, dir = None) -> None:
    subprocess.run(cmd.split(' '), cwd=dir)

@click.command()
@click.option("--git-uri", "-g", required=True, 
              help="URI of git repo to load in the environment")
@click.option("--compute-name", "-c", required=False,
              help="Compute name to migrate the environment to")
@click.option("--env-name", "-n", required=False,
              help="Environment name to start")
@click.pass_obj
def go(ez: Ez, git_uri, compute_name, env_name):
    """New experimental version of the run command that will remove the need
    to have repo2docker installed."""

    # If compute name is "-" OR there is no active compute defined, prompt
    # the user to select (or create) a compute
    if compute_name == "-":
        print("Select which VM to use from this list of VMs provisioned "
              f"in resource group {ez.resource_group}")
        compute_name = pick_vm(ez.resource_group)
    elif not compute_name:
        # Use the current compute_name or prompt if none defined
        if not ez.active_remote_compute:
            print("Select which VM to use from this list of VMs provisioned "
                f"in resource group {ez.resource_group}")
            compute_name = pick_vm(ez.resource_group)
        else:
            compute_name = ez.active_remote_compute
    else:
        print(f"Using {compute_name} to run {git_uri}")

    if env_name is None:
        env_name = git_uri.split("/")[-1]
        print(f"Using {env_name} (repo name) as the env name")

    # env_name will be used for local name of repository and is the path
    # on a remote machine as well

    # If the local path exists already, then we don't clone unless the
    # --force-clone switch is specified.

    # Clone the repository locally to a subdirectory of the directory where
    # the command is run from.
    local_env_path = f"{getcwd()}/{env_name}"

    if path.exists(local_env_path):
        print(f"UPDATING {git_uri} in {local_env_path}")
        exec_subprocess("git pull", local_env_path)
    else:
        git_cmd = f"git clone {git_uri} {local_env_path}"
        print(f"CLONING {git_uri} into {local_env_path}")
        exec_subprocess(git_cmd)

    # Read the ez.json configuration file at the root of the repository. This
    # needs to be read per project and contains some additional information:
    # - requires_gpu: True/False 
    # - base_container_image: name of the base container image

    env_json_path = f"{local_env_path}/ez.json"
    if path.exists(env_json_path):
        with open(env_json_path, "r") as f:
            ez_json = json.load(f)
    else:
        print("Need to have a default ez.json in the repo. Would you like "
              "me to generate one for you? (TODO)")
        # TODO: generate
        exit(1)

    # Determine if the target compute is local or remote. If local, we will
    # need to clone the GH repo locally, if remote, we will need to use SSH
    # tunneling to clone the repo onto the VM in a pre-configured location.

    # In the remote case, it needs to conditionally clone the git repo onto
    # the remote VM. If the repo was already cloned on the VM, then we need
    # to cd into the dir and git pull that repo. Otherwise just do the clone.
    remote_env_path = f"/home/{ez.user_name}/src/{env_name}"
    remote_pull_cmd = (f"[ -d '{remote_env_path}' ] && cd {remote_env_path} "
                       f"&& git pull")
    remote_clone_cmd = (f"[ ! -d '{remote_env_path}' ] && "
                        f"git clone {git_uri} {remote_env_path}")
    ssh_connection = (f"{ez.user_name}@{compute_name}.{ez.region}."
                      f"cloudapp.azure.com")
    remote_ssh_cmd = (
        f"ssh -o StrictHostKeyChecking=no "
        f"-i {ez.private_key_path} {ssh_connection} {remote_pull_cmd}"
    )
    print(f"Clone/update {git_uri} on {compute_name} at {remote_env_path}")
    exec_subprocess(remote_ssh_cmd)
    remote_ssh_cmd = (
        f"ssh -o StrictHostKeyChecking=no "
        f"-i {ez.private_key_path} {ssh_connection} {remote_clone_cmd}"
    )
    exec_subprocess(remote_ssh_cmd)

    # Check to see if the remote compute has the GPU capability if needed and
    # fail if it doesn't.

    # Start the remote compute if necessary. Wait for it to complete starting

    # If it is a remote launch, we will need to generate the information
    # needed for the local devcontainer.json file, as well as for the
    # settings.json file that contains the .vscode/settings.json file that
    # contains "docker.host": "ssh://user@machine.region.cloudapp.azure.com"
    settings_json = f"""
{{
    "docker.host": "ssh://{ssh_connection}",
}}
"""
    print(f"GENERATING .vscode/settings.json")
    vscode_dir = f"{local_env_path}/.vscode"
    settings_json_path = f"{vscode_dir}/settings.json"
    if not os.path.exists(vscode_dir):
        os.mkdir(vscode_dir)
    
    # Always overwrite these configuration files
    with open(settings_json_path, "wt+", encoding="utf-8") as f:
        f.write(settings_json)

    # Generate the devcontainer.json file. Much of this will eventually be
    # parameterized
    if compute_name == ".":
        mount_path = local_env_path
    else:
        mount_path = remote_env_path

    devcontainer_json = f"""
{{
    "containerUser": "root",
    "workspaceFolder": "/workspace",
    "workspaceMount": "source={mount_path},target=/workspace,type=bind,consistency=cached",
    "extensions": [
        "ms-python.python",
        "ms-python.vscode-pylance"
    ],
    "runArgs": [
        "--gpus=all",
        "--ipc=host",
    ],
    "dockerFile": "./Dockerfile",
}}
"""
    print(f"GENERATING .devcontainer/devcontainer.json")
    devcontainer_dir = f"{local_env_path}/.devcontainer"
    devcontainer_json_path = f"{devcontainer_dir}/devcontainer.json"
    if not os.path.exists(devcontainer_dir):
        os.mkdir(devcontainer_dir)
    with open(devcontainer_json_path, "wt+", encoding="utf-8") as f:
        f.write(devcontainer_json)

    # Generate the Dockerfile to be used by the project. The Dockerfile is
    # generated at launch time, and will have comments in it that will say
    # that it is machine-generated. Furthermore, the Dockerfile should be
    # excluded from the GH repo via .gitignore so that it doesn't pollute the
    # git history of the project. The Dockerfile will be generated and placed
    # in the .devcontainer directory locally or scp'd to the remote machine in
    # the well-known place where the cloned repo is stored:
    # /home/<ezuser>/ez/<GH repo name>

    # To generate the Dockerfile, information will be needed from the repo.
    # This first version of the command will just clone the repo into the
    # surrogate project directory. A future optimization will avoid the need
    # to clone the project locally as well.

    dockerfile = f"""
FROM {ez_json["base_container_image"]}

COPY requirements.txt /tmp/requirements.txt
WORKDIR /tmp
RUN pip install -v -r requirements.txt
"""
    print(f"GENERATING .devcontainer/Dockerfile")
    dockerfile_path = f"{devcontainer_dir}/Dockerfile"
    with open(dockerfile_path, "wt+", encoding="utf-8") as f:
        f.write(dockerfile)

    # If the resource group contains ACR, we could optionally build the 
    # docker image there and import it
    

    # Launch the project by launching VS Code using "code .". In the future
    # this command will be replaced with "devcontainer open ." but because of
    # the remote bug in devcontainer, we will avoid doing this for now and
    # manually reopen the VS Code project.
    print(f"LAUNCHING VS Code ... you will need to reload in remote container"
          f"by clicking the Reopen in Container button in the notification "
          f"box in the bottom right corner.")
    launch_vscode(ez, local_env_path)

    # Update ez state
    ez.active_remote_env = env_name
    ez.active_remote_compute = compute_name
    if compute_name != ".":
        ez.active_remote_compute_type = "vm"