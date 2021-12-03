j# ez

Commands for working with portable environments

## Why do you need it?

Imagine that you have a project, it runs on your computer, and you've created
a GitHub repo for it. What if you wanted to keep working on that same project
on another computer - could you do that? Before you say yes, here are some
things that you might need to do:

- install software/packages that your project needs to run
- install drivers if your project needs specialized hardware like a GPU
- mount an external file share that contains files that your project needs
- manage secrets for talking to services like GitHub
- configure your VS Code environment

None of those things adds any value to your life beyond getting your project
to run. Those things are time consuming and error-prone. It is hard to 
_reproduce_ your project on the other computer.

`ez` does all this for you by creating what we call a _portable environment_.
Once you have something working on a computer, the _portable environment_ can
be used to move your work to another computer without you needing to do
any additional work or make any changes to your code.

Imagine that you have been working on a machine learning model locally, but
you now need to train that model using the full dataset using more compute
resources on Azure. `ez` lets you do that with just a single command without
needing to have a devops engineer set everything up for you!

## What is it?

`ez` is a command line tool that lets you run GitHub repos on your local
computer or on Azure. This is the every-day command that you'll use in `ez`:

```sh
$ ez env go git@github.com:/jflam/fastai -c computer_name
```

There are two parameters to `ez env go`:

- the URI of a GitHub repo that you want to run
- the name of a computer that you want to run that repo on

`ez` will open the GitHub repo on `computer_name` and start a VS Code session
bound to the contents of that GitHub repo. 

![fast.ai notebooks running in VS Code](./images/screenshot.png | width=500)

You can do anything that you would normally do on a computer that you
configured yourself:

- you can commit changes back to your GitHub repo without needing to first
  setup your GitHub SSH keys
- you can read/write to files on a drive that is mounted into that repo - that
  drive can be accessed from other machines, or your local machine
- you can just run the code right away without needing to install additional
  software or libraries, provided that the repo has some _metadata_ that `ez`
  can use to create the Docker container image that it uses to run it
- you can SSH into that Docker container from a local machine without needing
  to configure SSH keys or remember anything other than `computer_name`
- you can copy files to/from that Docker container without needing to know
  anything more than some basic `scp` syntax

Click on the image beelow to watch this 3.5 minute video to see `ez` in action:

[![Getting Started with ez video](http://img.youtube.com/vi/u1nmx2rd5Jk/0.jpg)](http://www.youtube.com/watch?v=u1nmx2rd5Jk "Getting Started with ez and fast.ai")

WARNING: this is a proof-of-concept and is not production software. Think of
this as more of a prototype that can be used to better understand the problems
you have - a running spec if you will. Please do create issues so we can start
having some conversations about the things that will need to be done to 
satisfy real-work workflows.

## Getting Started


## How It Works

## Automated Installation and Configuration

`ez` has been developed and tested in two environments: Mac OS and Ubuntu
20.04 running under WSL 2 on Windows. It has not been tested on Windows yet. 
`ez` is a Python 3 application.

If you are running `ez` on Ubuntu in WSL 2, I've created a script to help
setup the environment for you. 

Before you can run this script, you will need to have [Docker
Desktop](https://docs.microsoft.com/en-us/windows/wsl/tutorials/wsl-containers)
installed with WSL 2 integrations enabled. You can learn more about installing
[WSL 2 from the Windows Store from
here](https://devblogs.microsoft.com/commandline/a-preview-of-wsl-in-the-microsoft-store-is-now-available/).

```sh
curl --remote-name https://gist.githubusercontent.com/jflam/bb75d1172607eba59edfec0157fa724b/raw/f4fdee178235d9a658be47ba1efd708b03e2d968/preinstall-ubuntu.sh
bash preinstall-ubuntu.sh
```

This script does the following things:

1. Installs a few dependencies: `git`, `curl`
1. Installs `Miniconda3`
1. Generates two SSH keys: `id_rsa_azure` and `id_rsa_github` that will be 
used to connect to GitHub and connect to resources that you create with
Azure.
1. Install the GitHub CLI
1. Install the Azure CLI
1. Logs into GitHub and Azure
1. Installs `ez` by cloning this repo
1. Initializes `ez`

## Manual installation

If you are installing manually from this repo and you have everything setup

To setup the tool for running in development mode, you will first need to
run from `src/`:

```
python setup.py develop
```

This will make it possible to continue to develop locally and have your 
changes immediately reflected each time you run `ez` from any directory.
