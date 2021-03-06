import click, glob, json, os, shutil, subprocess
import constants as C

from azutil import (get_active_env_name, get_vm_size, launch_vscode, 
    pick_vm, is_gpu, jit_activate_vm, 
    get_active_compute_name, mount_storage_account,
    get_compute_uri)
from exec import exec_cmd, exit_on_error
from ez_state import Ez, EzRuntime
from formatting import printf, printf_err
from typing import Any
from os import getcwd, path

@click.command()
@click.option("--name", "-n", required=True, default="",
    help=("compute node to use (default is the current active compute node)"))
@click.argument("src")
@click.argument("dest")
@click.pass_obj
def cp(runtime: EzRuntime, name: str, src: str, dest: str):
    """
Copy local files to/from an environment.

ez env cp <source> <dest>

The format of <source> and <dest> are important. Examples:

\b
foo.txt :.               Copy foo.txt to active environment /code dir
foo.txt :/remote/path    Copy foo.txt to active environment /remote/path dir
:/remote/path/foo.txt .  Copy active environment /remote/path/foo.txt locally
./*.txt :/remote/path    Copy local .txt files to active environment /remote/path
:/remote/path/*.txt ./   Copy active environment /remote/path/*.txt files locally
    """
    ez = runtime.current()
    if ez.active_remote_compute == ".":
        # TODO: this might not be the case though - let's get feedback on this
        printf_err("Not needed for locally running environments. You can "
            "copy files to/from the local directory of the GitHub repo "
            "using existing filesystem commands.")
        exit(1)

    if not ez.active_remote_env:
        printf_err("No running environment")
        exit(1)
    
    if not src:
        printf_err("Missing src parameter")
        exit(1)
    
    if not dest:
        printf_err("Missing dest parameter")
        exit(1)

    name = get_active_compute_name(runtime, name)
    
    if src.startswith(":") and dest.startswith(":"):
        printf_err("Both src and dest cannot start with ':' "
                   "to indicate remote")
        exit(1)
    elif src.startswith(":"):
        cmd = (f"scp -i {ez.private_key_path} {ez.user_name}@"
               f"{ez.active_remote_compute}.{ez.region}"
               f".cloudapp.azure.com:/home/{ez.user_name}/code/"
               f"{ez.active_remote_env}/{src[1:]} {dest}") 
        subprocess.run(cmd.split(' '))
    elif dest.startswith(":"):
        cmd = (f"scp -i {ez.private_key_path} {src} {ez.user_name}@"
               f"{ez.active_remote_compute}.{ez.region}"
               f".cloudapp.azure.com:/home/{ez.user_name}/code/"
               f"{ez.active_remote_env}/{dest[1:]}") 
        subprocess.run(cmd.split(' '))
    else:
        printf_err("One of src or dest must start with ':' to "
                   "indicate remote")
        exit(1)
    runtime.save()

@click.command()
@click.option("--name", "-n", default="", help="Name of target compute")
@click.option("--env-name", "-e", default="", 
    help="Environment name to start")
@click.pass_obj
def ssh(runtime: EzRuntime, name: str, env_name: str):
    """SSH to an environment"""
    ez = runtime.current()
    name = get_active_compute_name(runtime, name)
    env_name = get_active_env_name(runtime, env_name)

    if name != ".":
        # Run docker ps on the remote VM to figure out what the container id
        # of the running VS Code container is
        cmd = (f"ssh -i {ez.private_key_path} {ez.user_name}@{name}."
            f"{ez.region}.cloudapp.azure.com docker ps --format "
            "{{.Image}},{{.ID}}")
    else:
        # Run a local docker ps command to get the container id
        cmd = "docker ps --format {{.Image}},{{.ID}}"
    
    result = exec_cmd(cmd)
    exit_on_error(result)
    containers = result.stdout.strip().split("\n")
    vsc_containers = [c for c in containers if env_name in c]
    if len(vsc_containers) != 1:
        printf_err(f">1 container running with same env_name:")
        exit(1)

    image_name, container_id = vsc_containers[0].split(",")
    if name != ".":
        # Open a tunneled SSH connection into the running remote container
        cmd = (f"ssh -tt -i {ez.private_key_path} "
            f"{ez.user_name}@{name}.{ez.region}.cloudapp.azure.com "
            f"docker exec -it -w /workspace {container_id} /bin/bash")
        printf(f"opened SSH connection to container {container_id} running "
            f"using image {image_name} on "
            f"{name}.{ez.region}.cloudapp.azure.com")
    else:
        # Handle the local case
        cmd = f"docker exec -it -w /workspace {container_id} /bin/bash"
        printf(f"opened SSH connection to container {container_id} running "
               f"using image {image_name} on localhost")
    subprocess.run(cmd.split(' '))
    ez.active_remote_compute = name 
    ez.active_remote_env = env_name
    runtime.save()

@click.command()
@click.option("--name", "-n", required=True, default="",
    help="Compute name to migrate the environment to")
@click.option("--env-name", "-e", default="",
    help="Environment name to start")
@click.option("--mount", default="none",
    help="Mount {local|azure|none} drive to /data default none")
@click.pass_obj
def up(runtime: EzRuntime, name: str, env_name: str, mount: str):
    """Migrate the current environment to a new compute node"""

    ez = runtime.current()
    name = get_active_compute_name(runtime, name)
    env_name = get_active_env_name(runtime, env_name)

    # Let's assume that we are in a local environment for the purpose
    # of this. Later I will add heuristics to error out if this is not
    # the case.

    # Get the URI of the repo we are currently in
    result = exec_cmd("git config --get remote.origin.url")
    exit_on_error(result)
    git_remote_uri = result.stdout

    if git_remote_uri == "":
        printf_err(f"Directory {getcwd()} is not in a git repo")
        exit(1)

    printf(f"Migrating {git_remote_uri} to {name}")

    # Start the remote VM
    jit_activate_vm(runtime, name)
    ez.active_remote_compute = name

    # Check to see if there are uncommitted changes
    patch_file = None
    result = exec_cmd('git status | grep "Changes not staged for commit"')
    if result.exit_code == 0:
        result = exec_cmd("git stash")
        exit_on_error(result)
        result = exec_cmd("git stash show -p --binary > ~/tmp/changes.patch",
            description="Stashing uncommitted changes")
        exit_on_error(result)

        scp_cmd = (
            f"scp -i {ez.private_key_path} "
            f"~/tmp/changes.patch "
            f"{ez.user_name}@{name}.{ez.region}.cloudapp.azure.com:"
            f"/home/{ez.user_name}/changes.patch"
        )
        result = exec_cmd(scp_cmd, 
            description=f"Copying changes to {name}")
        exit_on_error(result)
        patch_file = "changes.patch"

    env_name = git_remote_uri.split("/")[-1]

    if mount == "azure" or mount == "local" or mount == "none":
        __go(runtime, ez, git_remote_uri, name, env_name, mount=mount, 
            patch_file=patch_file)
    else:
        printf_err("--mount must be azure|local|none")

    ez.active_remote_compute = name 
    ez.active_remote_env = env_name
    runtime.save()
    exit(0)

def clone_git_repo(git_uri: str, env_name: str) -> str:
    """Clone git repo to env_name returning the path to the repo"""
    # env_name will be used for local name of repository and is the path
    # on a remote machine as well

    # Clone the repository locally to a subdirectory of the directory where
    # the command is run from.
    local_env_path = f"{getcwd()}/{env_name}"
    if path.exists(local_env_path):
        result = exec_cmd("git pull", 
            description=f"Updating {git_uri} in {local_env_path}", 
            cwd=local_env_path)
        exit_on_error(result)
    else:
        git_cmd = f"git clone {git_uri} {local_env_path}"
        result = exec_cmd(git_cmd, description=f"cloning {git_uri} into "
            f"{local_env_path}")
        exit_on_error(result)
    
    return local_env_path

def read_repo_config(local_env_path: str) -> Any:
    """Read the repo's ez.json configuration file

    Args:
        local_env_path (str): Path to the repo

    Returns:
        Any: dictionary containing parsed repo configuration
    """
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
    
    return ez_json

def generate_dockerfile(ez: Ez, local_env_path: str, ez_json: Any):
    devcontainer_dir = f"{local_env_path}/.devcontainer"
    if not os.path.exists(devcontainer_dir):
        os.mkdir(devcontainer_dir)

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
    # surrogate project directory. A future optimization may avoid the need to
    # clone the project locally as well.

    # Copy files from the /build directory into the .devcontainer directory
    build_files = glob.glob(f"{local_env_path}/build/*")
    for file in build_files:
        if os.path.isfile(file):
            shutil.copy(file, devcontainer_dir)

    # Only generate a default Dockerfile if the user doesn't supply one in
    # their /build directory
    if not os.path.exists(f"{local_env_path}/build/Dockerfile"):
        # Need to generate build steps for cases where we have
        # requirements.txt or an environment.yml file in the /build directory
        if os.path.exists(f"{devcontainer_dir}/requirements.txt"):
            pip_install = """
COPY requirements.txt .
RUN pip install -v -r requirements.txt
"""
        else:
            pip_install = ""

        # The challenge here for both conda and pip is detecting whether the
        # base image contains Python or not or whether we should always
        # install Python onto the image.
        if os.path.exists(f"{devcontainer_dir}/environment.yml"):
            conda_install = f"""
COPY environment.yml .
RUN curl --remote-name {C.MINICONDA_INSTALLER} \\
    && chmod +x Miniconda3-latest-Linux-x86_64.sh \\
    && ./Miniconda3-latest-Linux-x86_64.sh -b 
ENV PATH="/home/{ez.user_name}/miniconda3/bin:$PATH"

RUN conda install -y mamba -n base -c conda-forge && \\
    mamba env create -f environment.yml
"""
        else:
            conda_install = ""

        dockerfile = f"""
FROM {ez_json["base_container_image"]}

USER root
RUN apt update \\
    && apt upgrade -y \\
    && apt install -y curl build-essential git vim

RUN useradd -r -u 1000 -m -d /home/{ez.user_name} {ez.user_name}
USER {ez.user_name}
WORKDIR /home/{ez.user_name}

{pip_install}
{conda_install}
    """
        dockerfile_path = f"{devcontainer_dir}/Dockerfile"
        with open(dockerfile_path, "w", encoding="utf-8") as f:
            f.write(dockerfile)

def build_container(ez: Ez, local_env_path: str, env_name: str, 
    compute_name: str, use_acr: bool):
    """Build container only if using ACR or running locally in WSL2

    Args:
        ez (Ez): [description]
        local_env_path (str): [description]
        env_name (str): [description]
        use_acr (bool): [description]
    """

    devcontainer_dir = f"{local_env_path}/.devcontainer"

    # Build the image using an ACR task if the --use-acr flag was set
    if use_acr:
        full_registry_name = (f"{ez.registry_name}.azurecr.io/"
                              f"{ez.workspace_name}:{env_name}")
        cmd = f"docker manifest inspect {full_registry_name}"
        result = exec_cmd(cmd, 
            description=f"checking if {full_registry_name} exists")

        # Returns 0 if image already exists, 1 if it does not
        if result.exit_code == 0:
            printf(f"Skipping build, {full_registry_name} exists already")
        else:
            cmd = (f"az acr build --registry {ez.registry_name} "
                f"--image {ez.workspace_name}:{env_name} .")
            result = exec_cmd(cmd, 
                description="Building container image using ACR Tasks", 
                cwd=devcontainer_dir)
            exit_on_error(result)
    
    # TODO: implement local docker build and generation of a WSL2 .vhdx
    # check compute_name as parameter

def clone_remote_repo(runtime: EzRuntime, ez: Ez, git_uri: str, compute_name: str, 
    env_name: str, patch_file: str):

    # Check to see if the remote compute has the GPU capability if needed
    # and fail if it doesn't.

    # TODO: Start the remote compute if necessary. Wait for it to complete
    # starting
    remote_env_path = f"/home/{ez.user_name}/code/{env_name}"

    # TODO: I don't like the design of the multiple commands - there
    # should be just a single command that conditionally runs expressions
    # on the remote machine. Keeping this for now in this mechanical
    # refactoring

    # In the remote case, it needs to conditionally clone the git repo
    # onto the remote VM. If the repo was already cloned on the VM, then
    # we need to cd into the dir and git pull that repo. Otherwise just do
    # the clone. We ignore the return codes here as the commands will
    # pass through the result of the conditional test which isn't 
    # actually indicating an error, just whether the conditional was
    # successful or not (and given the logic one of them MUST be 
    # unsuccessful).
    description = (f"clone/update {git_uri} on {compute_name} "
                    f"at {remote_env_path}")
    remote_pull_cmd = (f"[ -d '{remote_env_path}' ] && "
                        f"cd {remote_env_path} && git pull")
    result = exec_cmd(remote_pull_cmd, 
        uri=get_compute_uri(runtime, compute_name),
        private_key_path=ez.private_key_path,
        description=description)

    remote_clone_cmd = (f"[ ! -d '{remote_env_path}' ] && "
                        f"git clone {git_uri} {remote_env_path}")
    result = exec_cmd(remote_clone_cmd, 
        uri=get_compute_uri(runtime, compute_name),
        private_key_path=ez.private_key_path,
        description=description)

    # If a patch_file parameter is passed, then we need to apply the git
    # patch file that was copied onto the server. 
    if patch_file is not None:
        cmd = (f"pushd {remote_env_path} && git apply "
            f"/home/{ez.user_name}/{patch_file} && popd")
        result = exec_cmd(cmd, uri=get_compute_uri(runtime, compute_name), 
            private_key_path=ez.private_key_path, 
            description=f"Applying patch file: {patch_file}")

def write_settings_json(ez: Ez, compute_name: str, local_env_path: str):
    if compute_name != ".":
        # The .vscode directory contains a dynamically generated settings.json
        # file which points to the VM that the remote container will run on.

        # If it is a remote launch, we will need to generate the information
        # needed for the local devcontainer.json file, as well as for the
        # settings.json file that contains the .vscode/settings.json file that
        # contains "docker.host":
        # "ssh://user@machine.region.cloudapp.azure.com"

        # printf("Generating .vscode/settings.json")
        ssh_connection = (f"{ez.user_name}@{compute_name}.{ez.region}"
            ".cloudapp.azure.com")
        settings_json = f"""
    {{
    "docker.host": "ssh://{ssh_connection}",
    }}
    """
        vscode_dir = f"{local_env_path}/.vscode"
        settings_json_path = f"{vscode_dir}/settings.json"
        if not os.path.exists(vscode_dir):
            os.mkdir(vscode_dir)
        with open(settings_json_path, "w", encoding="utf-8") as f:
            f.write(settings_json)
    else:
        # local contrainer execution, so we need to generate a null 
        # .vscode/settings.json file (or delete existing file if there)

        # TODO: what really needs to be done is to remove an existing 
        # docker.host key from an existing settings.json file if it is there
        vscode_dir = f"{local_env_path}/.vscode"
        if os.path.exists(vscode_dir):
            if os.path.exists(f"{vscode_dir}/settings.json"):
                os.remove(f"{vscode_dir}/settings.json")

def write_devcontainer_json(runtime: EzRuntime, ez: Ez, compute_name: str, 
    env_name: str, local_env_path: str, ez_json: Any, use_acr: bool, 
    mount: str):

    # Generate the devcontainer.json file. Much of this will eventually be
    # parameterized

    # The .devcontainer directory contains dynamically generated artifacts:
    #
    # 1. The devcontainer.json file that instructs VS Code what to do to
    #    create the container
    # 2. The generated Dockerfile that instructs Docker what to do to build
    #    the container
    # 3. The requirements.txt or environment.yml file that is called from the
    #    Dockerfile to install the python modules needed to run the code
    # 4. Any additional python files that are used to initialize the
    #    container, e.g., downloading data, caching models etc. 
    #
    # Note that 3) and 4) are all contained within the /build directory at the
    # root of the GitHub repo and are copied into the .devcontainer directory.
    # Those files could all be run from the /build directory as well with
    # a hand-written Dockerfile

    remote_env_path = f"/home/{ez.user_name}/code/{env_name}"
    if compute_name == ".":
        mount_path = local_env_path
    else:
        mount_path = remote_env_path

    # The generated devcontainer.json file will differ based on whether we 
    # are letting remote containers generate the container on the VM or 
    # whether we will ask it to pull from ACR on the remote machine.

    # In the case where it pulls the image from ACR, the remote machine will
    # need to have the ability to access ACR, which means that it will need
    # to have an Azure public/private key pair in place unless I make the
    # ACR image publicly accessible.

    # Using tokens for this and the compute must be configured to use it
    # by logging in automatically into Docker when you ask it to.
    if use_acr:
        if ez.registry_name is None:
            printf_err(f"Resource group {ez.resource_group} "
                "does not have an Azure Container Registry configured.")
            exit(1)
        docker_source=f"""
    "image": "{ez.registry_name}.azurecr.io/{ez.workspace_name}:{env_name}",
""".strip()
    else:
        docker_source=f"""
    "dockerFile": "./Dockerfile",
""".strip()

    requires_gpu = ez_json["requires_gpu"]

    # Test whether the compute supports GPU or not
    if compute_name == ".":
        # Check if nvidia-smi is on command line as a crude check
        returncode = os.system(f"which nvidia-smi > /dev/null")
        compute_has_gpu = returncode == 0
    else:
        vm_size = get_vm_size(runtime, compute_name)
        compute_has_gpu = is_gpu(vm_size)

    if "run_args" in ez_json:
        runargs = ",".join(ez_json["run_args"])

    if requires_gpu and not compute_has_gpu:
        printf(f"Warning: repo requires a GPU and {compute_name} "
            "does not have one", indent=2)
    if requires_gpu and compute_has_gpu:
        # TODO: figure out how to right-size the --shm-size parameter
        # perhaps this means that we must let the user specify and default
        # to a reasonable value? What is clear is that --ipc=host is not a 
        # good idea as that requires the container to be run as root!

        # TODO: If ez.json has a run_args parameter, use it
        if "run_args" in ez_json:
            runargs = ",".join(f"\"{x}\"" for x in ez_json["run_args"])
        else:
            runargs = """
            "--gpus=all",
            "--shm-size=1g",
    """.strip()
    else:
        if "run_args" in ez_json:
            runargs = ",".join(f"\"{x}\"" for x in ez_json["run_args"])
        else:
            runargs = ""

    if compute_name == ".":
        # TODO: should this be interactive user?
        # container_user = getpass.getuser()
        container_user = ez.user_name
        ssh_dir = os.path.expanduser("~/.ssh")
    else:
        # If there is a container_user parameter in ez.json, use it
        container_user = ez.user_name
        if "container_user" in ez_json:
            container_user = ez_json["container_user"]
        ssh_dir = f"/home/{ez.user_name}/.ssh"
    
    ssh_target = f"/home/{container_user}/.ssh"
    ssh_mount = (f"\"source={ssh_dir},target={ssh_target},"
        f"type=bind,consistency=cached,readonly\",")

    # Valid combinations
    # Compute   local    azure         none
    # Local     ~/data   mount ~/data   x
    # Remote    ~/data   mount ~/data   x
    # Special case is if ez.file_share_name is None maps to none

    data_mount = ""
    if ez.file_share_name is not None:
        if mount == "local" or mount == "azure":
            if compute_name == ".":
                data_dir = os.path.expanduser("~/data")
            else:
                data_dir = f"/home/{ez.user_name}/data"
            data_mount = (f"\"source={data_dir},target=/data,type=bind,"
                f"consistency=cached\",")

    mounts = f"""
    "mounts": [
        {ssh_mount}
        {data_mount}
    ],
""".strip()

    workspace_mount = (f"\"source={mount_path},target=/workspace,type=bind,"
        "consistency=cached\"")
    devcontainer_json = f"""
{{
    {docker_source}
    "containerUser": "{container_user}",
    "workspaceFolder": "/workspace",
    "workspaceMount": {workspace_mount},
    {mounts}
    "extensions": [
        "ms-python.python",
        "ms-python.vscode-pylance"
    ],
    "runArgs": [
        {runargs}
    ],
}}
"""
    devcontainer_json_path = f"{local_env_path}/.devcontainer/devcontainer.json"
    with open(devcontainer_json_path, "w", encoding="utf-8") as f:
        f.write(devcontainer_json)

def mount_data_drive(runtime: EzRuntime, ez: Ez, compute_name: str, 
    mount: str):

    # Mount /data drive only if azure
    if mount == "azure":
        if compute_name == ".":
            mount_path = os.path.expanduser("~/data")
        else:
            mount_path = f"/home/{ez.user_name}/data"
        mount_storage_account(runtime, compute_name, mount_path)

def run_vscode(runtime: EzRuntime, ez: Ez, compute_name: str, 
    env_name: str, local_env_path: str):

    # Launch the project by launching VS Code using "devcontainer open .". 
    printf(f"Launching VS Code...", indent=2)
    launch_vscode(runtime, local_env_path)

    # Update ez state
    ez.active_remote_env = env_name
    ez.active_remote_compute = compute_name
    if compute_name != ".":
        ez.active_remote_compute_type = "vm"

def __go(runtime: EzRuntime, ez: Ez, git_uri: str, compute_name: str, 
    env_name: str, use_acr: bool=False, build: bool=False, mount: str="none",
    patch_file: str=None):

    local_env_path = clone_git_repo(git_uri, env_name)
    ez_json = read_repo_config(local_env_path)
    generate_dockerfile(ez, local_env_path, ez_json)
    build_container(ez, local_env_path, env_name, compute_name, use_acr)

    if compute_name != ".":
        clone_remote_repo(runtime, ez, git_uri, compute_name, env_name, 
            patch_file)

    write_settings_json(ez, compute_name, local_env_path)
    write_devcontainer_json(runtime, ez, compute_name, env_name, 
        local_env_path, ez_json, use_acr, mount)

    mount_data_drive(runtime, ez, compute_name, mount)
    run_vscode(runtime, ez, compute_name, env_name, local_env_path)

@click.command()
@click.option("--git-uri", "-g", required=True, prompt="URI of GitHub repo",
    help="URI of git repo to load in the environment")
@click.option("--name", "-n", default="",
    help="Compute name to migrate the environment to")
@click.option("--env-name", "-e", default="",
    help="Environment name to start")
@click.option("--mount", default="none",
    help="Mount {local|azure|none} drive to /data default none")
@click.option("--use-acr", is_flag=True, default=False,
    help="Generate container using Azure Container Registry")
@click.option("--build", is_flag=True, default=False,
    help="When used with --use-acr forces a build of the container")
@click.pass_obj
def go(runtime: EzRuntime, git_uri: str, name: str, env_name: str, mount: str, 
    use_acr: bool, build: bool):
    """Create and run an environment"""

    # If compute name is "-" OR there is no active compute defined, prompt
    # the user to select (or create) a compute
    ez = runtime.current()
    if name == "-":
        print("Select which VM to use from this list of VMs provisioned "
              f"in resource group {ez.resource_group}")
        name = pick_vm(ez.resource_group)
    elif name == "":
        # Use the current compute_name or prompt if none defined
        if ez.active_remote_compute == "":
            print("Select which VM to use from this list of VMs provisioned "
                f"in resource group {ez.resource_group}")
            name = pick_vm(ez.resource_group)
        else:
            name = ez.active_remote_compute
    else:
        printf(f"using {name} to run {git_uri}", indent=2)

    if env_name == "":
        env_name = git_uri.split("/")[-1]
        printf(f"using {env_name} (repo name) as the env name", indent=2)

    if mount == "azure" or mount == "local" or mount == "none":
        __go(runtime, ez, git_uri, name, env_name, use_acr, build, mount)
    else:
        printf_err("--mount must be azure|local|none")
    runtime.save()
    exit(0)