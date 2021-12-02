import click, glob, json, os, random, shutil, subprocess, uuid
import constants as C

from azutil import (build_container_image, get_vm_size, launch_vscode, 
    pick_vm, generate_vscode_project, is_gpu, jit_activate_vm, 
    get_active_compute_name, get_compute_size, mount_storage_account,
    get_compute_uri)
from exec import exec_cmd, exit_on_error
from ez_state import Ez, EzRuntime
from formatting import printf, printf_err
from os import getcwd, path

def launch_user_interface(runtime: EzRuntime, user_interface, 
    path_to_vscode_project, jupyter_port, token):
    """Bind user_interface to the running instance"""
    ez = runtime.current()
    if user_interface == "code":
        printf(f"launch VS Code {path_to_vscode_project}")
        launch_vscode(runtime, path_to_vscode_project)
    elif user_interface == "notebook" or user_interface == "lab":
        printf(f"launch Classic Jupyter "
              f"http://localhost:{jupyter_port}?token={token}")

def run_k8s(runtime: EzRuntime, env_name, git_uri, jupyter_port, compute_name,
            user_interface, git_clone, token, has_gpu, force_generate):
    """DEPRECATED"""
    ez = runtime.current()
    printf_err("k8s support needs reimplementation")
    exit(1)

    # path_to_vscode_project = generate_vscode_project(runtime, getcwd(), git_uri, 
    #                                                  jupyter_port, token, 
    #                                                  ".", has_gpu, 
    #                                                  force_generate, True)

    # # ASSUME if path_to_vscode_project exists that image built alredy
    # if not path.exists(path_to_vscode_project):
    #     build_cmd = (f"jupyter-repo2docker --image-name jflam/{env_name} "
    #                 f"--no-run {path_to_vscode_project}")
    #     print(f"BUILD Docker image locally: {build_cmd}")
    #     result = exec_cmd(build_cmd)
    #     exit_on_error(result)
    #     docker_cmd = (f"docker push jflam/{env_name}")
    #     print(f"PUSH Docker image to Docker Hub: {docker_cmd}")
    #     result = exec_cmd(docker_cmd)
    #     exit_on_error(result)

    # launch_user_interface(runtime, user_interface, path_to_vscode_project, 
    #                       jupyter_port, token)

    # jupyter_variant = "notebook"
    # if user_interface == "lab":
    #     jupyter_variant = "lab"

    # kdo_cmd = (f"kdo -p {jupyter_port}:{jupyter_port} "
    #            "--spec '{\"resources\":{\"limits\":{\"nvidia.com/gpu\":\"1\"}}}' "
    #            f"jflam/{env_name} "
    #            f"nohup jupyter {jupyter_variant} --no-browser "
    #            f"--port {jupyter_port} --ip=0.0.0.0 "
    #            f"--NotebookApp.token={token} .")

    # # kdo blocks while syncing local filesystem into the pod
    # # CTRL+C will terminate.
    # print(f"START pod {kdo_cmd}")
    # print("TERMINATE using CTRL+C")
    # result = exec_cmd(kdo_cmd)
    # exit_on_error(result)

def run_vm(runtime: EzRuntime, env_name, git_uri, jupyter_port, compute_name,
           user_interface, git_clone, token, has_gpu, force_generate):
    """DEPRECATED"""
    ez = runtime.current()
    build_container_image(runtime, env_name, git_uri, jupyter_port, 
        compute_name, user_interface, git_clone)
    path_to_vscode_project = generate_vscode_project(runtime, getcwd(), git_uri, 
                                                     jupyter_port, token, 
                                                     compute_name, has_gpu, 
                                                     force_generate)

    launch_user_interface(runtime, user_interface, path_to_vscode_project, 
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
def run(runtime: EzRuntime, env_name, git_uri, user_interface, compute_name, 
    git_clone, force_generate):
    """DEPRECATED"""
    ez = runtime.current()
    printf_err("deprecated: Use ez env go instead")
    exit(0)

    compute_name = get_active_compute_name(runtime, compute_name)

    # Initialize context
    ez.active_remote_compute = compute_name
    ez.active_remote_env = env_name
    ez.local_repo_name = path.basename(git_uri)

    jupyter_port = random.randint(1024, 8192)
    token = uuid.uuid4().hex 

    compute_size = get_compute_size(runtime, compute_name)
    has_gpu = is_gpu(compute_size)

    if ez.active_remote_compute_type == 'vm':
        run_vm(runtime, env_name, git_uri, jupyter_port, compute_name,
               user_interface, git_clone, token, has_gpu, force_generate)
    elif ez.active_remote_compute_type == 'k8s':
        run_k8s(runtime, env_name, git_uri, jupyter_port, compute_name,
                user_interface, git_clone, token, has_gpu, force_generate)
    else:
        print(f"Unknown active_remote_compute_type in ~/.ez.conf: "
            f"{ez.active_remote_compute_type}")
        exit(1)
    exit(0)

@click.command()
@click.pass_obj
def ls(runtime: EzRuntime):
    """List running environments"""
    pass

@click.command()
@click.option("--compute-name", "-c", 
              help=("compute node to use (default is the "
              "current active compute node)"))
@click.argument("src")
@click.argument("dest")
@click.pass_obj
def cp(runtime: EzRuntime, compute_name: str, src: str, dest: str):
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

    compute_name = get_active_compute_name(runtime, compute_name)
    
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

@click.command()
@click.option("--compute-name", "-c", required=False,
              help="Compute name to migrate the environment to")
@click.option("--env-name", "-n", required=False,
              help="Environment name to start")
@click.pass_obj
def ssh(runtime: EzRuntime, compute_name, env_name):
    """SSH to an environment"""
    ez = runtime.current()
    if not ez.active_remote_compute:
        if not compute_name:
            printf_err("--compute-name parameter must be specified "
                       "because there isn't an active compute environment.")
            exit(1)
    else:
        compute_name = ez.active_remote_compute

    if not ez.active_remote_env:
        if not env_name:
            printf_err("--env-name parameter must be specified "
                       "because there isn't an active environment.")    
            exit(1)
    else:
        env_name = ez.active_remote_env

    if compute_name != ".":
        # Run docker ps on the remote VM to figure out what the container id
        # of the running VS Code container is
        cmd = (f"ssh -i {ez.private_key_path} {ez.user_name}@{compute_name}."
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
    if compute_name != ".":
        # Open a tunneled SSH connection into the running remote container
        cmd = (f"ssh -tt -i {ez.private_key_path} "
            f"{ez.user_name}@{compute_name}.{ez.region}.cloudapp.azure.com "
            f"docker exec -it -w /workspace {container_id} /bin/bash")
        printf(f"opened SSH connection to container {container_id} running "
            f"using image {image_name} on "
            f"{compute_name}.{ez.region}.cloudapp.azure.com")
    else:
        # Handle the local case
        cmd = f"docker exec -it -w /workspace {container_id} /bin/bash"
        printf(f"opened SSH connection to container {container_id} running "
               f"using image {image_name} on localhost")
    subprocess.run(cmd.split(' '))

@click.command()
@click.pass_obj
def stop(runtime: EzRuntime):
    pass

@click.command()
@click.option("--compute-name", "-c", required=False,
              help="Compute name to migrate the environment to")
@click.option("--env-name", "-n", required=False,
              help="Environment name to start")
@click.pass_obj
def up(runtime: EzRuntime, compute_name, env_name):
    """Migrate the current environment to a new compute node"""

    # Let's assume that we are in a local environment for the purpose
    # of this. Later I will add heuristics to error out if this is not
    # the case.

    # Get the URI of the repo we are currently in
    ez = runtime.current()
    result = exec_cmd("git config --get remote.origin.url")
    exit_on_error(result)
    git_remote_uri = result.stdout

    if git_remote_uri == "":
        printf_err(f"Directory {getcwd()} is not in a git repo")
        exit(1)

    printf(f"Migrating {git_remote_uri} to {compute_name}")

    # Start the remote VM
    jit_activate_vm(runtime, compute_name)
    ez.active_remote_compute = compute_name

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
            f"{ez.user_name}@{compute_name}.{ez.region}.cloudapp.azure.com:"
            f"/home/{ez.user_name}/changes.patch"
        )
        result = exec_cmd(scp_cmd, 
            description=f"Copying changes to {compute_name}")
        exit_on_error(result)
        patch_file = "changes.patch"

    env_name = git_remote_uri.split("/")[-1]
    __go(runtime, git_remote_uri, compute_name, env_name, mount_drive=True, 
        patch_file=patch_file)

    exit(0)

def __go(runtime: EzRuntime, ez: Ez, git_uri: str, compute_name: str, env_name: str, 
    use_acr: bool=False, build: bool=False, mount: str="none",
    patch_file: str=None):
    # env_name will be used for local name of repository and is the path
    # on a remote machine as well

    # If the local path exists already, then we don't clone unless the
    # --force-clone switch is specified.

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

    devcontainer_dir = f"{local_env_path}/.devcontainer"
    devcontainer_json_path = f"{devcontainer_dir}/devcontainer.json"
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
    # printf("Copying /build files to /.devcontainer")
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

RUN apt update \\
    && apt upgrade -y \\
    && apt install -y curl build-essential git vim

RUN useradd -r -u 1000 -m -d /home/{ez.user_name} {ez.user_name}
USER {ez.user_name}
WORKDIR /home/{ez.user_name}

{pip_install}
{conda_install}
    """
        # printf("Generating default .devcontainer/Dockerfile")
        dockerfile_path = f"{devcontainer_dir}/Dockerfile"
        with open(dockerfile_path, "w", encoding="utf-8") as f:
            f.write(dockerfile)

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

    if compute_name != ".":
        # Check to see if the remote compute has the GPU capability if needed
        # and fail if it doesn't.

        # TODO: Start the remote compute if necessary. Wait for it to complete
        # starting
        remote_env_path = f"/home/{ez.user_name}/code/{env_name}"

        # In the remote case, it needs to conditionally clone the git repo
        # onto the remote VM. If the repo was already cloned on the VM, then
        # we need to cd into the dir and git pull that repo. Otherwise just do
        # the clone.
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

        # Apply the patch file if it exists on the server
        if patch_file is not None:
            cmd = (f"pushd {remote_env_path} && git apply "
                f"/home/{ez.user_name}/{patch_file} && popd")
            result = exec_cmd(cmd, uri=get_compute_uri(runtime, compute_name), 
                private_key_path=ez.private_key_path, 
                description=f"Applying patch file: {patch_file}")

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

    # printf("Generating .devcontainer/devcontainer.json")
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
        # HACK: false for the demo
        compute_has_gpu = False
    else:
        vm_size = get_vm_size(runtime, compute_name)
        compute_has_gpu = is_gpu(vm_size)

    if requires_gpu and not compute_has_gpu:
        printf(f"Warning: repo requires a GPU and {compute_name} "
            "does not have one", indent=2)
    if requires_gpu and compute_has_gpu:
        # TODO: figure out how to right-size the --shm-size parameter
        # perhaps this means that we must let the user specify and default
        # to a reasonable value? What is clear is that --ipc=host is not a 
        # good idea as that requires the container to be run as root!
        runargs = """
        "--gpus=all",
        "--shm-size=1g",
""".strip()
    else:
        runargs = ""

    if compute_name == ".":
        # container_user = getpass.getuser()
        container_user = ez.user_name
        ssh_dir = os.path.expanduser("~/.ssh")
    else:
        container_user = ez.user_name
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
    with open(devcontainer_json_path, "w", encoding="utf-8") as f:
        f.write(devcontainer_json)

    # Mount /data drive only if azure
    if mount == "azure":
        if compute_name == ".":
            mount_path = os.path.expanduser("~/data")
        else:
            mount_path = f"/home/{ez.user_name}/data"
        mount_storage_account(runtime, compute_name, mount_path)

    # Launch the project by launching VS Code using "code .". In the future
    # this command will be replaced with "devcontainer open ." but because of
    # the remote bug in devcontainer, we will avoid doing this for now and
    # manually reopen the VS Code project.
    printf(f"Launching VS Code ... you will need to reload in "
           f"remote container by clicking the Reopen in Container button in "
           f"the notification box in the bottom right corner.", indent=2)
    launch_vscode(runtime, local_env_path)

    # Update ez state
    ez.active_remote_env = env_name
    ez.active_remote_compute = compute_name
    if compute_name != ".":
        ez.active_remote_compute_type = "vm"

@click.command()
@click.option("--git-uri", "-g", required=True, 
              help="URI of git repo to load in the environment")
@click.option("--compute-name", "-c", required=False,
              help="Compute name to migrate the environment to")
@click.option("--env-name", "-n", required=False,
              help="Environment name to start")
@click.option("--mount", default="None",
              help="Mount {local|azure|none} drive to /data default none")
@click.option("--use-acr", is_flag=True, default=False,
              help="Generate container using Azure Container Registry")
@click.option("--build", is_flag=True, default=False,
              help="When used with --use-acr forces a build of the container")
@click.pass_obj
def go(runtime: EzRuntime, git_uri, compute_name, env_name, mount: str, 
    use_acr: bool, build: bool):
    """Create and run an environment"""

    # If compute name is "-" OR there is no active compute defined, prompt
    # the user to select (or create) a compute
    ez = runtime.current()
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
        printf(f"using {compute_name} to run {git_uri}", indent=2)

    if env_name is None:
        env_name = git_uri.split("/")[-1]
        printf(f"using {env_name} (repo name) as the env name", indent=2)

    if mount == "azure" or mount == "local" or mount == "none":
        __go(runtime, ez, git_uri, compute_name, env_name, use_acr, build, 
            mount)
    else:
        printf_err("--mount must be azure|local|none")
    exit(0)