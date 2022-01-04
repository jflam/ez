# This is a script that will construct a sample vnet on Azure with
#
# 1. A vnet and a new resource group for it
# 2. A VM that I can connect to
# 3. A Gateway that I can use to connect to it
# 4. An Azure Storage account that contains an Azure file share that is mounted to the VM
# 5. Some ability for me to connect to it from my local Mac
# 6. A way to ssh into the VM once my local mac is connected to the vnet
# 7. A way to mount the Azure file share locally and in the VM

export ez_rg="ezws-westus2-private-rg"
export ez_region="westus2"
export ez_vnet="ez-westus2-private-vnet"
export ez_gateway="ez-westus2-private-gateway"
export ez_storage="ezwestus2privatestorage"
export ez_share="ezdata"
export ez_gateway_subnet="GatewaySubnet"
export ez_vm_subnet="ezvmsubnet"
export ez_gateway_ip="ez-westus2-gateway-ip"
export ez_vpn_client_address_pool="172.16.201.0/24"

# Create a new azure resource group
az group create --location $ez_region --name $ez_rg

# Delete resource group
# az group delete --name $ez_rg

# Create a new vnet
az network vnet create --name $ez_vnet -g $ez_rg --location $ez_region \
  --address-prefix 10.0.0.0/16 --subnet-name $ez_gateway_subnet \
  --subnet-prefix 10.0.1.0/24

# Create a default subnet on the vnet with address range 10.1.0.0/24
# az network vnet subnet create --name $ez_gateway_subnet -g $ez_rg \
#   --address-prefixes 10.1.0.0/24 --vnet-name $ez_vnet

# Create an Azure Storage account in the resource group
az storage account create --name $ez_storage -g $ez_rg 

# Create an Azure File Share
az storage share-rm create --name $ez_share -g $ez_rg --storage-account $ez_storage \
  --quota 512

# List network account rules
# az storage account network-rule list -g $ez_rg -n $ez_storage --query virtualNetworkRules

# Update default access rules
az storage account update -g $ez_rg --name $ez_storage --default-action Deny

# Enable service endpoint for Azure Storage on vnet
az network vnet subnet update -g $ez_rg --vnet-name $ez_vnet -n $ez_gateway_subnet --service-endpoints "Microsoft.Storage"

# Add network rule for the vnet and subnet
subnetid=$(az network vnet subnet show -g $ez_rg --vnet-name $ez_vnet --name $ez_gateway_subnet --query id --output tsv)
az storage account network-rule add -g $ez_rg --account-name $ez_storage --subnet $subnetid

# Delete Azure Storage Account (doesn't work? Needed to delete using Portal? WTF?!)
# az storage account delete --name $ez_storage -g $ez_rg

# Create a local root cert
sudo ipsec pki --gen --outform pem > ~/.cer/caKey.pem
sudo ipsec pki --self --in ~/.cer/caKey.pem --dn "CN=VPN CA" --ca \
  --outform pem > ~/.cer/caCert.pem
openssl x509 -in ~/.cer/caCert.pem -outform der | base64 > ~/.cer/root.cer

# Create local machine cert
export CLIENTCERTNAME="client"

sudo ipsec pki --gen --outform pem > ~/.cer/"${CLIENTCERTNAME}Key.pem"
sudo ipsec pki --pub --in ~/.cer/"${CLIENTCERTNAME}Key.pem" \
  | ipsec pki --issue --cacert ~/.cer/caCert.pem --cakey ~/.cer/caKey.pem \
  --dn "CN=${CLIENTCERTNAME}" --san "${CLIENTCERTNAME}" --flag clientAuth \
  --outform pem > ~/.cer/"${CLIENTCERTNAME}Cert.pem"
openssl pkcs12 -in ~/.cer/"${CLIENTCERTNAME}Cert.pem" \
  -inkey ~/.cer/"${CLIENTCERTNAME}Key.pem" -certfile ~/.cer/caCert.pem \
  -export -out ~/.cer/"${CLIENTCERTNAME}.p12" -password="pass:"

# Create a public IP address (non-zonal?)
az network public-ip create -g $ez_rg --name $ez_gateway_ip --version IPv4 \
  --sku Standard 

# Create a new gateway for the vnet
az network vnet-gateway create --name $ez_gateway -g $ez_rg --sku VpnGw1 \
  --vnet $ez_vnet --public-ip-addresses $ez_gateway_ip --location $ez_region

# Configure VPN client address pool
az network vnet-gateway update --address-prefixes $ez_vpn_client_address_pool \
  --client-protocol IkeV2 --name $ez_gateway -g $ez_rg

# Upload local root cert
az network vnet-gateway root-cert create -g $ez_rg -n rootcert \
  --gateway-name $ez_gateway --public-cert-data ~/.cer/root.cer

# Delete an existing vnet gateway
# az network vnet-gateway delete --name $ez_gateway -g $ez_rg

# Create a nic for a virtual network
# az network nic create --name vnetNic -g $ez_rg --vnet-name $ez_vnet --subnet $ez_gateway_subnet

# Create a vnet for the VMs
az network vnet subnet create -g $ez_rg --vnet-name $ez_vnet -n $ez_vm_subnet \
    --address-prefixes 10.0.0.0/24 --network-security-group MyNsg --route-table MyRouteTable

# Create a VM in the resource group 
az vm create --name ez-private-testvm -g $ez_rg --image UbuntuLTS \
  --vnet-name $ez_vnet --subnet $ez_vm_subnet --ssh-key-values ~/.ssh/id_rsa_azure.pub \
  --size Standard_B1s --admin-username ezuser