import pulumi
import pulumi_awsx as awsx
import pulumi_eks as eks
import pulumi_kubernetes as kubernetes
from pulumi_kubernetes.yaml import ConfigFile

# Get some values from the Pulumi configuration (or use defaults)
config = pulumi.Config()
min_cluster_size = config.get_float("minClusterSize", 1)
max_cluster_size = config.get_float("maxClusterSize", 3)
desired_cluster_size = config.get_float("desiredClusterSize", 2)
eks_node_instance_type = config.get("eksNodeInstanceType", "t3.small")
vpc_network_cidr = config.get("vpcNetworkCidr", "10.0.0.0/16")

# Create a namespace configuration file to load in namespaces.YAML
# Creates namespaces based on configration files from NS___Config files
ns_dev_config = ConfigFile("ns_dev_config", file="nsDevConfig.yaml")
ns_alpha_config = ConfigFile("ns_alpha_config", file="nsAlphaConfig.yml")
ns_prod_config = ConfigFile("ns_prod_config", file="nsProdConfig.yml")

devNS = pulumi.Output.from_input(ns_dev_config.get_resource(
		"apps/v1/Deployment",
		"hello-world", namespace="dev"
))
alphaNS = pulumi.Output.from_input(ns_alpha_config.get_resource(
		"apps/v1/Deployment",
		"hello-world", namespace="alpha"
))
prodNS = pulumi.Output.from_input(ns_prod_config.get_resource(
		"apps/v1/Deployment",
		"hello-world", namespace="prod"
))

# Create a VPC for the EKS cluster
eks_vpc = awsx.ec2.Vpc(
		"eks-vpc",
		enable_dns_hostnames=True,
		cidr_block=vpc_network_cidr)

# Create the EKS cluster
eks_cluster = eks.Cluster(
		"eks-cluster",
		# Put the cluster in the new VPC created earlier
		vpc_id=eks_vpc.vpc_id,
		# Public subnets will be used for load balancers
		public_subnet_ids=eks_vpc.public_subnet_ids,
		# Private subnets will be used for cluster nodes
		private_subnet_ids=eks_vpc.private_subnet_ids,
		# Change configuration values to change any of the following settings
		instance_type=eks_node_instance_type,
		desired_capacity=desired_cluster_size,
		min_size=min_cluster_size,
		max_size=max_cluster_size,
		# Do not give worker nodes a public IP address
		node_associate_public_ip_address=False,
		# Uncomment the next two lines for private cluster (VPN access required)
		# endpoint_private_access=true,
		# endpoint_public_access=false
)

eks_provider = kubernetes.Provider(
		"eks-provider",
		kubeconfig=eks_cluster.kubeconfig_json
)

test_nginx_deployment = kubernetes.apps.v1.Deployment(
		"test-nginx-deployment",
		metadata=kubernetes.meta.v1.ObjectMetaArgs(
				labels={
						"appClass": "test-nginx-deployment",
				},
		),
		spec=kubernetes.apps.v1.DeploymentSpecArgs(
				replicas=2,
				selector=kubernetes.meta.v1.LabelSelectorArgs(
						match_labels={
								"appClass": "test-nginx-deployment",
						},
				),
				template=kubernetes.core.v1.PodTemplateSpecArgs(
						metadata=kubernetes.meta.v1.ObjectMetaArgs(
								labels={
										"appClass": "test-nginx-deployment",
								},
						),
						spec=kubernetes.core.v1.PodSpecArgs(
								containers=[kubernetes.core.v1.ContainerArgs(
										name="test-nginx-deployment",
										image="nginx",
										ports=[kubernetes.core.v1.ContainerPortArgs(
												name="http",
												container_port=80,
										)],
								)],
						),
				),
		),
		opts=pulumi.ResourceOptions(provider=eks_provider))
test_nginx_service = kubernetes.core.v1.Service(
		"test-nginx-service",
		metadata=kubernetes.meta.v1.ObjectMetaArgs(
				labels={
						"appClass": "test-nginx-deployment",
				},
		),
		spec=kubernetes.core.v1.ServiceSpecArgs(
				type="LoadBalancer",
				ports=[kubernetes.core.v1.ServicePortArgs(
						port=80,
						target_port="http",
				)],
				selector={
						"appClass": "test-nginx-deployment",
				},
		),
		opts=pulumi.ResourceOptions(provider=eks_provider))

# Export values to use elsewhere
pulumi.export("kubeconfig", eks_cluster.kubeconfig)
pulumi.export("vpcId", eks_vpc.vpc_id)
pulumi.export(
		"url",
		test_nginx_service.status.load_balancer.ingress[0].hostname
)
# Exports kubernetes namespace resources
pulumi.export("dev", devNS)
pulumi.export("alpha", alphaNS)
pulumi.export("prod", prodNS)

