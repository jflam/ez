# bash script for setting up pre-requisites for installing Ez on Mac
# This script has some pre-requisites of its own too:
# 
# 1. Need to have Docker installed on the Mac
# 2. Need to have Homebrew installed

# Detect docker
if ! command -v docker &> /dev/null 
then 
  echo "You need to install Docker first: https://docs.docker.com/get-docker/"
  exit
fi

# Detect brew
if ! command -v brew &> /dev/null 
then
  echo "You need to install Homebrew first: https://brew.sh/"
  exit 
fi

# Warm up by updating system
brew update && brew upgrade 

# Install git, curl
# sudo apt install git curl keychain -y
brew install git curl

# Install Python via miniconda silently
cd ~/ && mkdir ~/tmp 
cd ~/tmp
curl https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-x86_64.sh \
  --remote-name
bash Miniconda3-latest-MacOSX-x86_64.sh -b

# Configure conda into current zsh
echo 'eval "$(~/miniconda3/bin/conda shell.zsh hook)"' >> ~/.zshrc

# Do the same thing but within this session
eval "$(~/miniconda3/bin/conda shell.zsh hook)"

# Generate SSH keys for accessing Azure and GitHub
# You will need to enter passphrases for these
# TODO: remove the -q -N flags later once we figure out passphrase management
ssh-keygen -t ed25519 -C "Github key" -f ~/.ssh/id_rsa_github -q -N ""
ssh-keygen -t rsa -b 4096 -C "Azure key" -f ~/.ssh/id_rsa_azure -q -N ""

# Map the keys to the appropriate domains
cat > ~/.ssh/config << EOF
Host github.com
  AddKeysToAgent yes
  IdentityFile ~/.ssh/id_rsa_github

Host *.cloudapp.azure.com
  AddKeysToAgent yes
  IdentityFile ~/.ssh/id_rsa_azure
EOF

# Install GitHub CLI
brew install gh

# Install the Azure CLI
brew install azure-cli

# Log into GitHub
gh auth login

# Log into Azure
az login

# Install ez
mkdir ~/src 
cd ~/src
git clone https://github.com/jflam/ez
cd ez/src 
python setup.py install

# Initialize ez
ez init

# Reload bash environment
exec bash