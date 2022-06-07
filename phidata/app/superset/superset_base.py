from collections import OrderedDict
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from typing_extensions import Literal

from phidata.app.db import DbApp
from phidata.app import PhidataApp, PhidataAppArgs
from phidata.constants import (
    SCRIPTS_DIR_ENV_VAR,
    STORAGE_DIR_ENV_VAR,
    META_DIR_ENV_VAR,
    PRODUCTS_DIR_ENV_VAR,
    NOTEBOOKS_DIR_ENV_VAR,
    WORKSPACE_CONFIG_DIR_ENV_VAR,
    PHIDATA_RUNTIME_ENV_VAR,
)
from phidata.infra.docker.resource.network import DockerNetwork
from phidata.infra.docker.resource.container import DockerContainer
from phidata.infra.docker.resource.group import (
    DockerResourceGroup,
    DockerBuildContext,
)
from phidata.infra.k8s.create.apps.v1.deployment import CreateDeployment, RestartPolicy
from phidata.infra.k8s.create.core.v1.secret import CreateSecret
from phidata.infra.k8s.create.core.v1.service import CreateService, ServiceType
from phidata.infra.k8s.create.core.v1.config_map import CreateConfigMap
from phidata.infra.k8s.create.core.v1.container import CreateContainer, ImagePullPolicy
from phidata.infra.k8s.create.core.v1.volume import (
    CreateVolume,
    HostPathVolumeSource,
    VolumeType,
)
from phidata.infra.k8s.create.common.port import CreatePort
from phidata.infra.k8s.create.group import CreateK8sResourceGroup
from phidata.infra.k8s.resource.group import (
    K8sResourceGroup,
    K8sBuildContext,
)
from phidata.utils.common import (
    get_image_str,
    get_default_container_name,
    get_default_configmap_name,
    get_default_secret_name,
    get_default_service_name,
    get_default_deploy_name,
    get_default_pod_name,
    get_default_volume_name,
)
from phidata.utils.cli_console import print_error, print_warning
from phidata.utils.log import logger


class SupersetBaseArgs(PhidataAppArgs):
    name: str = "superset"
    version: str = "1"
    enabled: bool = True

    # Image args
    image_name: str = "apache/superset"
    image_tag: str = "latest"
    entrypoint: Optional[Union[str, List]] = None
    command: Optional[Union[str, List]] = None

    # Mount the workspace directory on the container
    mount_workspace: bool = False
    workspace_volume_name: Optional[str] = None
    # Path to mount the workspace volume under
    # This is the parent directory for the workspace on the container
    # i.e. the ws is mounted as a subdir in this dir
    # eg: if ws name is: idata, workspace_dir would be: /usr/local/idata
    workspace_parent_container_path: str = "/usr/local"
    # NOTE: On DockerContainers the workspace_root_path is mounted to workspace_dir
    # because we assume that DockerContainers are running locally on the user's machine
    # On K8sContainers, we load the workspace_dir from git using a git-sync sidecar container
    create_git_sync_sidecar: bool = True
    git_sync_repo: Optional[str] = None
    git_sync_branch: Optional[str] = None
    git_sync_wait: int = 1
    # But when running k8s locally, we can mount the workspace using
    # host path as well.
    k8s_mount_local_workspace: bool = False

    # Superset resources directory relative to the workspace_root
    # This directory contains all the files required by superset.
    # eg: docker-bootstrap.sh
    # This dir is mounted to the `/app/docker` directory on the container
    resources_dir: str = "superset"
    resources_dir_container_path: str = "/app/docker"
    mount_resources: bool = True
    resources_volume_name: Optional[str] = None
    # skips downloading resources if the resources_dir exists
    cache_resources: bool = True

    # Set the SUPERSET_CONFIG_PATH env var
    superset_config_path: Optional[str] = None

    # Set the REQUIREMENTS_LOCAL env var
    # defaults to "/app/docker/requirements-local.txt"
    requirements_local: Optional[str] = None

    # Set the PYTHONPATH env var
    # defaults to "/app/pythonpath"
    python_path: Optional[str] = None

    # Configure Superset database
    # Get database details using DbApp
    db_app: Optional[DbApp] = None
    # Provide database details
    # Set the DATABASE_USER env var
    db_user: str = "superset"
    # Set the DATABASE_PASSWORD env var
    db_password: str = "superset"
    # Set the DATABASE_DB env var
    db_schema: str = "superset"
    # Set the DATABASE_HOST env var
    db_host: str = "db"
    # Set the DATABASE_PORT env var
    db_port: int = 5432
    # Set the DATABASE_DIALECT env var
    db_dialect: str = "postgresql+psycopg2"
    # Superset db connections in the format { conn_id: conn_url }
    db_connections: Optional[Dict] = None

    # Configure superset redis
    # Get redis details using PhidataApp
    redis_app: Optional[Any] = None
    # Provide redis details
    # Set the REDIS_HOST env var
    redis_host: str = "redis"
    # Set the REDIS_PORT env var
    redis_port: int = 6379

    # Set the FLASK_ENV env var
    flask_env: str = "production"
    # Set the SUPERSET_ENV env var
    superset_env: str = "production"
    # Set the SUPERSET_LOAD_EXAMPLES env var
    superset_load_examples: str = "yes"

    # Configure the container
    container_name: Optional[str] = None
    image_pull_policy: ImagePullPolicy = ImagePullPolicy.IF_NOT_PRESENT
    container_detach: bool = True
    container_auto_remove: bool = True
    container_remove: bool = True

    # Add container labels
    container_labels: Optional[Dict[str, Any]] = None
    # NOTE: Available only for Docker
    # Add volumes to DockerContainer
    # container_volumes is a dictionary which adds the volumes to mount
    # inside the container. The key is either the host path or a volume name,
    # and the value is a dictionary with 2 keys:
    #   bind - The path to mount the volume inside the container
    #   mode - Either rw to mount the volume read/write, or ro to mount it read-only.
    # For example:
    # {
    #   '/home/user1/': {'bind': '/mnt/vol2', 'mode': 'rw'},
    #   '/var/www': {'bind': '/mnt/vol1', 'mode': 'ro'}
    # }
    container_volumes: Optional[Dict[str, dict]] = None

    # Open a container port if open_container_port=True
    open_container_port: bool = False
    # Port number on the container
    container_port: int = 8000
    # Port name: Only used by the K8sContainer
    container_port_name: str = "http"
    # Host port: Only used by the DockerContainer
    container_host_port: int = 8000

    # Open the app port if open_app_port=True
    open_app_port: bool = True
    # App port number on the container
    # Set the SUPERSET_PORT env var
    app_port: int = 8088
    # Only used by the K8sContainer
    app_port_name: str = "app"
    # Only used by the DockerContainer
    app_host_port: int = 8088

    # Add env variables to container env
    env: Optional[Dict[str, str]] = None
    # Read env variables from a file in yaml format
    env_file: Optional[Path] = None
    # Configure the ConfigMap used for env variables that are not Secret
    config_map_name: Optional[str] = None
    # Configure the Secret used for env variables that are Secret
    secret_name: Optional[str] = None
    # Read secrets from a file in yaml format
    secrets_file: Optional[Path] = None

    # Configure the deployment
    deploy_name: Optional[str] = None
    pod_name: Optional[str] = None
    replicas: int = 1
    pod_node_selector: Optional[Dict[str, str]] = None
    restart_policy: RestartPolicy = RestartPolicy.ALWAYS
    termination_grace_period_seconds: Optional[int] = None
    # Add deployment labels
    deploy_labels: Optional[Dict[str, Any]] = None
    # Determine how to spread the deployment across a topology
    # Key to spread the pods across
    topology_spread_key: Optional[str] = None
    # The degree to which pods may be unevenly distributed
    topology_spread_max_skew: Optional[int] = None
    # How to deal with a pod if it doesn't satisfy the spread constraint.
    topology_spread_when_unsatisfiable: Optional[
        Literal["DoNotSchedule", "ScheduleAnyway"]
    ] = None

    # Configure the app service
    create_app_service: bool = False
    app_service_name: Optional[str] = None
    app_service_type: Optional[ServiceType] = None
    # The port that will be exposed by the service.
    app_service_port: int = 8088
    # The node_port that will be exposed by the service if app_service_type = ServiceType.NODE_PORT
    app_node_port: Optional[int] = None
    # The app_target_port is the port to access on the pods targeted by the service.
    # It can be the port number or port name on the pod.
    app_target_port: Optional[Union[str, int]] = None
    # Add labels to app service
    app_service_labels: Optional[Dict[str, Any]] = None


class SupersetBase(PhidataApp):
    def __init__(
        self,
        name: str = "superset",
        version: str = "1",
        enabled: bool = True,
        # Image args,
        image_name: str = "apache/superset",
        image_tag: str = "latest",
        entrypoint: Optional[Union[str, List]] = None,
        command: Optional[Union[str, List]] = None,
        # Mount the workspace directory on the container,
        mount_workspace: bool = False,
        workspace_volume_name: Optional[str] = None,
        # Path to mount the workspace volume under,
        # This is the parent directory for the workspace on the container,
        # i.e. the ws is mounted as a subdir in this dir,
        # eg: if ws name is: idata, workspace_dir would be: /usr/local/idata,
        workspace_parent_container_path: str = "/usr/local",
        # NOTE: On DockerContainers the workspace_root_path is mounted to workspace_dir,
        # because we assume that DockerContainers are running locally on the user's machine,
        # On K8sContainers, we load the workspace_dir from git using a git-sync sidecar container,
        create_git_sync_sidecar: bool = True,
        git_sync_repo: Optional[str] = None,
        git_sync_branch: Optional[str] = None,
        git_sync_wait: int = 1,
        # But when running k8s locally, we can mount the workspace using,
        # host path as well.,
        k8s_mount_local_workspace: bool = False,
        # Superset resources directory relative to the workspace_root,
        # This directory contains all the files required by superset.,
        # eg: docker-bootstrap.sh,
        # This dir is mounted to the `/app/docker` directory on the container,
        resources_dir: str = "superset",
        resources_dir_container_path: str = "/app/docker",
        mount_resources: bool = True,
        resources_volume_name: Optional[str] = None,
        # skips downloading resources if the resources_dir exists,
        cache_resources: bool = True,
        # Set the SUPERSET_CONFIG_PATH env var,,
        superset_config_path: Optional[str] = None,
        # Set the REQUIREMENTS_LOCAL env var,
        # defaults to "/app/docker/requirements-local.txt",
        requirements_local: Optional[str] = None,
        # Set the PYTHONPATH env var,
        # defaults to "/app/pythonpath",
        python_path: Optional[str] = None,
        # Configure Superset database,
        # Get database details using DbApp,
        db_app: Optional[DbApp] = None,
        # Provide database details,
        # Set the DATABASE_USER env var,
        db_user: Optional[str] = None,
        # Set the DATABASE_PASSWORD env var,
        db_password: Optional[str] = None,
        # Set the DATABASE_DB env var,
        db_schema: Optional[str] = None,
        # Set the DATABASE_HOST env var,
        db_host: Optional[str] = None,
        # Set the DATABASE_PORT env var,
        db_port: Optional[int] = None,
        # Set the DATABASE_DIALECT env var,
        db_dialect: str = "postgresql+psycopg2",
        # Superset db connections in the format { conn_id: conn_url },
        db_connections: Optional[Dict] = None,
        # Configure superset redis,
        # Get redis details using PhidataApp,
        redis_app: Optional[Any] = None,
        # Provide redis details,
        # Set the REDIS_HOST env var,
        redis_host: str = "redis",
        # Set the REDIS_PORT env var,
        redis_port: int = 6379,
        # Set the FLASK_ENV env var,
        flask_env: str = "production",
        # Set the SUPERSET_ENV env var,
        superset_env: str = "production",
        # Set the SUPERSET_LOAD_EXAMPLES env var,
        superset_load_examples: str = "yes",
        # Configure the container,
        container_name: Optional[str] = None,
        image_pull_policy: ImagePullPolicy = ImagePullPolicy.IF_NOT_PRESENT,
        container_detach: bool = True,
        container_auto_remove: bool = True,
        container_remove: bool = True,
        # Add container labels,
        container_labels: Optional[Dict[str, Any]] = None,
        # NOTE: Available only for Docker,
        # Add volumes to DockerContainer,
        # container_volumes is a dictionary which adds the volumes to mount,
        # inside the container. The key is either the host path or a volume name,,
        # and the value is a dictionary with 2 keys:,
        #   bind - The path to mount the volume inside the container,
        #   mode - Either rw to mount the volume read/write, or ro to mount it read-only.,
        # For example:,
        # {,
        #   '/home/user1/': {'bind': '/mnt/vol2', 'mode': 'rw'},,
        #   '/var/www': {'bind': '/mnt/vol1', 'mode': 'ro'},
        # },
        container_volumes: Optional[Dict[str, dict]] = None,
        # Open a container port if open_container_port=True,
        open_container_port: bool = False,
        # Port number on the container,
        container_port: int = 8000,
        # Port name: Only used by the K8sContainer,
        container_port_name: str = "http",
        # Host port: Only used by the DockerContainer,
        container_host_port: int = 8000,
        # Open the app port if open_app_port=True,
        open_app_port: bool = False,
        # App port number on the container,
        app_port: int = 8088,
        # Only used by the K8sContainer,
        app_port_name: str = "app",
        # Only used by the DockerContainer,
        app_host_port: int = 8088,
        # Add env variables to container env,
        env: Optional[Dict[str, str]] = None,
        # Read env variables from a file in yaml format,
        env_file: Optional[Path] = None,
        # Configure the ConfigMap used for env variables that are not Secret,
        config_map_name: Optional[str] = None,
        # Configure the Secret used for env variables that are Secret,
        secret_name: Optional[str] = None,
        # Read secrets from a file in yaml format,
        secrets_file: Optional[Path] = None,
        # Configure the deployment,
        deploy_name: Optional[str] = None,
        pod_name: Optional[str] = None,
        replicas: int = 1,
        pod_node_selector: Optional[Dict[str, str]] = None,
        restart_policy: RestartPolicy = RestartPolicy.ALWAYS,
        termination_grace_period_seconds: Optional[int] = None,
        # Add deployment labels,
        deploy_labels: Optional[Dict[str, Any]] = None,
        # Determine how to spread the deployment across a topology,
        # Key to spread the pods across,
        topology_spread_key: Optional[str] = None,
        # The degree to which pods may be unevenly distributed,
        topology_spread_max_skew: Optional[int] = None,
        # How to deal with a pod if it doesn't satisfy the spread constraint.,
        topology_spread_when_unsatisfiable: Optional[
            Literal["DoNotSchedule", "ScheduleAnyway"],
        ] = None,
        # Configure the app service,
        create_app_service: bool = False,
        app_service_name: Optional[str] = None,
        app_service_type: Optional[ServiceType] = None,
        # The port that will be exposed by the service.,
        app_service_port: int = 8088,
        # The node_port that will be exposed by the service if app_service_type = ServiceType.NODE_PORT,
        app_node_port: Optional[int] = None,
        # The app_target_port is the port to access on the pods targeted by the service.,
        # It can be the port number or port name on the pod.,
        app_target_port: Optional[Union[str, int]] = None,
        # Add labels to app service,
        app_service_labels: Optional[Dict[str, Any]] = None,
        # Additional args
        # If True, use cached resources
        # i.e. skip resource creation/deletion if active resources with the same name exist.
        use_cache: bool = True,
    ):
        super().__init__()
        try:
            self.args: SupersetBaseArgs = SupersetBaseArgs(
                name=name,
                version=version,
                enabled=enabled,
                image_name=image_name,
                image_tag=image_tag,
                entrypoint=entrypoint,
                command=command,
                mount_workspace=mount_workspace,
                workspace_volume_name=workspace_volume_name,
                workspace_parent_container_path=workspace_parent_container_path,
                create_git_sync_sidecar=create_git_sync_sidecar,
                git_sync_repo=git_sync_repo,
                git_sync_branch=git_sync_branch,
                git_sync_wait=git_sync_wait,
                k8s_mount_local_workspace=k8s_mount_local_workspace,
                resources_dir=resources_dir,
                resources_dir_container_path=resources_dir_container_path,
                mount_resources=mount_resources,
                resources_volume_name=resources_volume_name,
                cache_resources=cache_resources,
                superset_config_path=superset_config_path,
                requirements_local=requirements_local,
                python_path=python_path,
                db_app=db_app,
                db_user=db_user,
                db_password=db_password,
                db_schema=db_schema,
                db_host=db_host,
                db_port=db_port,
                db_dialect=db_dialect,
                db_connections=db_connections,
                redis_app=redis_app,
                redis_host=redis_host,
                redis_port=redis_port,
                flask_env=flask_env,
                superset_env=superset_env,
                superset_load_examples=superset_load_examples,
                container_name=container_name,
                image_pull_policy=image_pull_policy,
                container_detach=container_detach,
                container_auto_remove=container_auto_remove,
                container_remove=container_remove,
                container_labels=container_labels,
                container_volumes=container_volumes,
                open_container_port=open_container_port,
                container_port=container_port,
                container_port_name=container_port_name,
                container_host_port=container_host_port,
                open_app_port=open_app_port,
                app_port=app_port,
                app_port_name=app_port_name,
                app_host_port=app_host_port,
                env=env,
                env_file=env_file,
                config_map_name=config_map_name,
                secret_name=secret_name,
                secrets_file=secrets_file,
                deploy_name=deploy_name,
                pod_name=pod_name,
                replicas=replicas,
                pod_node_selector=pod_node_selector,
                restart_policy=restart_policy,
                termination_grace_period_seconds=termination_grace_period_seconds,
                deploy_labels=deploy_labels,
                topology_spread_key=topology_spread_key,
                topology_spread_max_skew=topology_spread_max_skew,
                topology_spread_when_unsatisfiable=topology_spread_when_unsatisfiable,
                create_app_service=create_app_service,
                app_service_name=app_service_name,
                app_service_type=app_service_type,
                app_service_port=app_service_port,
                app_node_port=app_node_port,
                app_target_port=app_target_port,
                app_service_labels=app_service_labels,
                use_cache=use_cache,
            )
        except Exception as e:
            logger.error(f"Args for {self.__class__.__name__} are not valid")
            raise

    def get_container_name(self) -> str:
        return self.args.container_name or get_default_container_name(self.args.name)

    def get_app_service_name(self) -> str:
        return self.args.app_service_name or get_default_service_name(self.args.name)

    def get_app_service_port(self) -> int:
        return self.args.app_service_port

    def get_env_data_from_file(self) -> Optional[Dict[str, str]]:
        env_file_path = self.args.env_file
        if (
            env_file_path is not None
            and env_file_path.exists()
            and env_file_path.is_file()
        ):
            if env_file_path.suffix == ".yaml":
                import yaml

                # logger.debug(f"Reading {env_file_path}")
                env_data_from_file = yaml.safe_load(env_file_path.read_text())
                if env_data_from_file is not None and isinstance(
                    env_data_from_file, dict
                ):
                    return env_data_from_file
                else:
                    print_error(f"Invalid env_file: {env_file_path}")
            else:
                print_warning(f"Skipping: {env_file_path}")
        return None

    def get_secret_data_from_file(self) -> Optional[Dict[str, str]]:
        secrets_file_path = self.args.secrets_file
        if (
            secrets_file_path is not None
            and secrets_file_path.exists()
            and secrets_file_path.is_file()
        ):
            if secrets_file_path.suffix == ".yaml":
                import yaml

                # logger.debug(f"Reading {secrets_file_path}")
                secret_data_from_file = yaml.safe_load(secrets_file_path.read_text())
                if secret_data_from_file is not None and isinstance(
                    secret_data_from_file, dict
                ):
                    return secret_data_from_file
                else:
                    print_error(f"Invalid secrets_file: {secrets_file_path}")
            else:
                print_warning(f"Skipping: {secrets_file_path}")
        return None

    ######################################################
    ## Docker Resources
    ######################################################

    def get_docker_rg(
        self, docker_build_context: DockerBuildContext
    ) -> Optional[DockerResourceGroup]:

        app_name = self.args.name
        logger.debug(f"Building {app_name} DockerResourceGroup")

        # Workspace paths
        if self.workspace_root_path is None:
            logger.error("Invalid workspace_root_path")
            return None
        workspace_name = self.workspace_root_path.stem
        workspace_root_container_path = Path(
            self.args.workspace_parent_container_path
        ).joinpath(workspace_name)

        # Container Environment
        container_env: Dict[str, str] = {
            # Env variables used by data workfloapp and data assets
            "PHI_WORKSPACE_PARENT": str(self.args.workspace_parent_container_path),
            "PHI_WORKSPACE_ROOT": str(workspace_root_container_path),
            PHIDATA_RUNTIME_ENV_VAR: "superset",
        }

        if self.args.superset_config_path is not None:
            container_env["SUPERSET_CONFIG_PATH"] = self.args.superset_config_path

        if self.args.requirements_local is not None:
            container_env["REQUIREMENTS_LOCAL"] = self.args.requirements_local

        if self.args.python_path is not None:
            container_env["PYTHONPATH"] = self.args.python_path

        # Superset db connection
        db_user = self.args.db_user
        db_password = self.args.db_password
        db_schema = self.args.db_schema
        db_host = self.args.db_host
        db_port = self.args.db_port
        db_dialect = self.args.db_dialect
        if self.args.db_app is not None and isinstance(self.args.db_app, DbApp):
            logger.debug(f"Reading db connection details from: {self.args.db_app.name}")
            if db_user is None:
                db_user = self.args.db_app.get_db_user()
            if db_password is None:
                db_password = self.args.db_app.get_db_password()
            if db_schema is None:
                db_schema = self.args.db_app.get_db_schema()
            if db_host is None:
                db_host = self.args.db_app.get_db_host_docker()
            if db_port is None:
                db_port = self.args.db_app.get_db_port_docker()
            if db_dialect is None:
                db_dialect = self.args.db_app.get_db_driver()
        db_connection_url = (
            f"{db_dialect}://{db_user}:{db_password}@{db_host}:{db_port}/{db_schema}"
        )

        if db_user is not None:
            container_env["DATABASE_USER"] = db_user

        if db_password is not None:
            container_env["DATABASE_PASSWORD"] = db_password

        if db_schema is not None:
            container_env["DATABASE_DB"] = db_schema

        if db_host is not None:
            container_env["DATABASE_HOST"] = db_host

        if db_port is not None:
            container_env["DATABASE_PORT"] = str(db_port)

        if db_dialect is not None:
            container_env["DATABASE_DIALECT"] = db_dialect

        if self.args.flask_env is not None:
            container_env["FLASK_ENV"] = self.args.flask_env

        if self.args.superset_env is not None:
            container_env["SUPERSET_ENV"] = self.args.superset_env

        if self.args.superset_load_examples is not None:
            container_env["SUPERSET_LOAD_EXAMPLES"] = self.args.superset_load_examples

        # Superset redis connection
        redis_host = self.args.redis_host
        redis_port = self.args.redis_port
        if self.args.redis_app is not None and isinstance(self.args.redis_app, DbApp):
            logger.debug(
                f"Reading redis connection details from: {self.args.redis_app.name}"
            )
            if redis_host is None:
                redis_host = self.args.redis_app.get_db_host_docker()
            if redis_port is None:
                redis_port = self.args.redis_app.get_db_port_docker()

        if redis_host is not None:
            container_env["REDIS_HOST"] = redis_host

        if redis_port is not None:
            container_env["REDIS_PORT"] = str(redis_port)

        # Update the container env using env_file
        env_data_from_file = self.get_env_data_from_file()
        if env_data_from_file is not None:
            container_env.update(env_data_from_file)

        # Update the container env using secrets_file
        secret_data_from_file = self.get_secret_data_from_file()
        if secret_data_from_file is not None:
            container_env.update(secret_data_from_file)

        # Update the container env with user provided env, this overwrites any existing variables
        if self.args.env is not None and isinstance(self.args.env, dict):
            container_env.update(self.args.env)

        # Container Volumes
        # container_volumes is a dictionary which configures the volumes to mount
        # inside the container. The key is either the host path or a volume name,
        # and the value is a dictionary with 2 keys:
        #   bind - The path to mount the volume inside the container
        #   mode - Either rw to mount the volume read/write, or ro to mount it read-only.
        # For example:
        # {
        #   '/home/user1/': {'bind': '/mnt/vol2', 'mode': 'rw'},
        #   '/var/www': {'bind': '/mnt/vol1', 'mode': 'ro'}
        # }
        container_volumes = self.args.container_volumes or {}
        # Create a volume for the workspace dir
        if self.args.mount_workspace:
            workspace_root_path_str = str(self.workspace_root_path)
            workspace_root_container_path_str = str(workspace_root_container_path)
            logger.debug(f"Mounting: {workspace_root_path_str}")
            logger.debug(f"\tto: {workspace_root_container_path_str}")
            container_volumes[workspace_root_path_str] = {
                "bind": workspace_root_container_path_str,
                "mode": "rw",
            }
        # Create a volume for aapp config
        if self.args.mount_resources:
            resources_dir_path = str(
                self.workspace_root_path.joinpath(self.args.resources_dir)
            )
            logger.debug(f"Mounting: {resources_dir_path}")
            logger.debug(f"\tto: {self.args.resources_dir_container_path}")
            container_volumes[resources_dir_path] = {
                "bind": self.args.resources_dir_container_path,
                "mode": "ro",
            }

        # Container Ports
        # container_ports is a dictionary which configures the ports to bind
        # inside the container. The key is the port to bind inside the container
        #   either as an integer or a string in the form port/protocol
        # and the value is the corresponding port to open on the host.
        # For example:
        #   {'2222/tcp': 3333} will expose port 2222 inside the container as port 3333 on the host.
        container_ports: Dict[str, int] = {}

        # if open_container_port = True
        if self.args.open_container_port:
            container_ports[
                str(self.args.container_port)
            ] = self.args.container_host_port

        # if open_app_port = True
        # 1. Set the app_port in the container env
        # 2. Open the app_port
        if self.args.open_app_port:
            # Set the app port in the container_env
            container_env["SUPERSET_PORT"] = str(self.args.app_port)
            # Open the port
            container_ports[str(self.args.app_port)] = self.args.app_host_port

        # Create the container
        docker_container = DockerContainer(
            name=self.get_container_name(),
            image=get_image_str(self.args.image_name, self.args.image_tag),
            entrypoint=self.args.entrypoint,
            command=self.args.command,
            detach=self.args.container_detach,
            auto_remove=self.args.container_auto_remove,
            remove=self.args.container_remove,
            stdin_open=True,
            tty=True,
            labels=self.args.container_labels,
            environment=container_env,
            network=docker_build_context.network,
            ports=container_ports if len(container_ports) > 0 else None,
            volumes=container_volumes,
            use_cache=self.args.use_cache,
        )
        logger.debug(f"Container Env: {docker_container.environment}")

        docker_rg = DockerResourceGroup(
            name=app_name,
            enabled=self.args.enabled,
            network=DockerNetwork(name=docker_build_context.network),
            containers=[docker_container],
        )
        return docker_rg

    def init_docker_resource_groups(
        self, docker_build_context: DockerBuildContext
    ) -> None:
        docker_rg = self.get_docker_rg(docker_build_context)
        if docker_rg is not None:
            if self.docker_resource_groups is None:
                self.docker_resource_groups = OrderedDict()
            self.docker_resource_groups[docker_rg.name] = docker_rg

    ######################################################
    ## K8s Resources
    ######################################################

    def get_k8s_rg(
        self, k8s_build_context: K8sBuildContext
    ) -> Optional[K8sResourceGroup]:

        app_name = self.args.name
        logger.debug(f"Building {app_name} K8sResourceGroup")

        # Define K8s resources
        config_maps: List[CreateConfigMap] = []
        secrets: List[CreateSecret] = []
        volumes: List[CreateVolume] = []
        containers: List[CreateContainer] = []
        services: List[CreateService] = []
        ports: List[CreatePort] = []

        # Workspace paths
        if self.workspace_root_path is None:
            logger.error("Invalid workspace_root_path")
            return None
        workspace_name = self.workspace_root_path.stem
        workspace_root_container_path = Path(
            self.args.workspace_parent_container_path
        ).joinpath(workspace_name)
        requirements_file_container_path = workspace_root_container_path.joinpath(
            self.args.requirements_file_path
        )
        scripts_dir_container_path = (
            workspace_root_container_path.joinpath(self.scripts_dir)
            if self.scripts_dir
            else None
        )
        storage_dir_container_path = (
            workspace_root_container_path.joinpath(self.storage_dir)
            if self.storage_dir
            else None
        )
        meta_dir_container_path = (
            workspace_root_container_path.joinpath(self.meta_dir)
            if self.meta_dir
            else None
        )
        products_dir_container_path = (
            workspace_root_container_path.joinpath(self.products_dir)
            if self.products_dir
            else None
        )
        notebooks_dir_container_path = (
            workspace_root_container_path.joinpath(self.notebooks_dir)
            if self.notebooks_dir
            else None
        )
        workspace_config_dir_container_path = (
            workspace_root_container_path.joinpath(self.workspace_config_dir)
            if self.workspace_config_dir
            else None
        )

        # Superset db connection
        db_user = self.args.db_user
        db_password = self.args.db_password
        db_schema = self.args.db_schema
        db_host = self.args.db_host
        db_port = self.args.db_port
        db_driver = self.args.db_driver
        if self.args.db_app is not None and isinstance(self.args.db_app, DbApp):
            logger.debug(f"Reading db connection details from: {self.args.db_app.name}")
            if db_user is None:
                db_user = self.args.db_app.get_db_user()
            if db_password is None:
                db_password = self.args.db_app.get_db_password()
            if db_schema is None:
                db_schema = self.args.db_app.get_db_schema()
            if db_host is None:
                db_host = self.args.db_app.get_db_host_k8s()
            if db_port is None:
                db_port = self.args.db_app.get_db_port_k8s()
            if db_driver is None:
                db_driver = self.args.db_app.get_db_driver()
        db_connection_url = (
            f"{db_driver}://{db_user}:{db_password}@{db_host}:{db_port}/{db_schema}"
        )

        # Container pythonpath
        python_path = self.args.python_path or str(workspace_root_container_path)

        # Container Environment
        container_env: Dict[str, str] = {
            # Env variables used by data workfloapp and data assets
            "PHI_WORKSPACE_PARENT": str(self.args.workspace_parent_container_path),
            "PHI_WORKSPACE_ROOT": str(workspace_root_container_path),
            "PYTHONPATH": python_path,
            PHIDATA_RUNTIME_ENV_VAR: "superset",
            SCRIPTS_DIR_ENV_VAR: str(scripts_dir_container_path),
            STORAGE_DIR_ENV_VAR: str(storage_dir_container_path),
            META_DIR_ENV_VAR: str(meta_dir_container_path),
            PRODUCTS_DIR_ENV_VAR: str(products_dir_container_path),
            NOTEBOOKS_DIR_ENV_VAR: str(notebooks_dir_container_path),
            WORKSPACE_CONFIG_DIR_ENV_VAR: str(workspace_config_dir_container_path),
            "INSTALL_REQUIREMENTS": str(self.args.install_requirements),
            "REQUIREMENTS_FILE_PATH": str(requirements_file_container_path),
            "MOUNT_WORKSPACE": str(self.args.mount_workspace),
            # Print env when the container starts
            "PRINT_ENV_ON_LOAD": str(self.args.print_env_on_load),
            # Env variables used by Superset
            # INIT_AIRFLOW env var is required for phidata to create DAGs
            "INIT_AIRFLOW": str(True),
            "AIRFLOW_ENV": self.args.superset_env,
            "WAIT_FOR_DB": str(self.args.wait_for_db),
            "WAIT_FOR_DB_INIT": str(self.args.wait_for_db_init),
            "INIT_AIRFLOW_DB": str(self.args.init_superset_db),
            "UPGRADE_AIRFLOW_DB": str(self.args.upgrade_superset_db),
            "DB_USER": str(db_user),
            "DB_PASSWORD": str(db_password),
            "DB_SCHEMA": str(db_schema),
            "DB_HOST": str(db_host),
            "DB_PORT": str(db_port),
            "WAIT_FOR_REDIS": str(self.args.wait_for_redis),
            "AIRFLOW__CORE__LOAD_EXAMPLES": str(self.args.load_examples),
            "CREATE_AIRFLOW_ADMIN_USER": str(self.args.create_superset_admin_user),
            "AIRFLOW__CORE__EXECUTOR": str(self.args.executor),
        }

        # Set the AIRFLOW__DATABASE__SQL_ALCHEMY_CONN
        if "None" not in db_connection_url:
            logger.debug(f"AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: {db_connection_url}")
            container_env["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"] = db_connection_url

        # Set the AIRFLOW__CORE__DAGS_FOLDER
        if self.args.mount_workspace and self.args.use_products_as_superset_dags:
            container_env["AIRFLOW__CORE__DAGS_FOLDER"] = str(
                products_dir_container_path
            )
        elif self.args.superset_dags_path is not None:
            container_env["AIRFLOW__CORE__DAGS_FOLDER"] = self.args.superset_dags_path

        # Set the AIRFLOW__CONN_ variables
        if self.args.db_connections is not None:
            for conn_id, conn_url in self.args.db_connections.items():
                try:
                    af_conn_id = str("AIRFLOW_CONN_{}".format(conn_id)).upper()
                    container_env[af_conn_id] = conn_url
                except Exception as e:
                    logger.exception(e)
                    continue

        if self.args.executor == "CeleryExecutor":
            # Superset celery result backend
            celery_result_backend_driver = (
                self.args.db_result_backend_driver or db_driver
            )
            celery_result_backend_url = f"{celery_result_backend_driver}://{db_user}:{db_password}@{db_host}:{db_port}/{db_schema}"
            # Set the AIRFLOW__CELERY__RESULT_BACKEND
            if "None" not in celery_result_backend_url:
                container_env[
                    "AIRFLOW__CELERY__RESULT_BACKEND"
                ] = celery_result_backend_url

            # Superset celery broker url
            redis_password = (
                f"{self.args.redis_password}@" if self.args.redis_password else ""
            )
            redis_schema = self.args.redis_schema
            redis_host = self.args.redis_host
            redis_port = self.args.redis_port
            redis_driver = self.args.redis_driver
            if self.args.redis_app is not None and isinstance(
                self.args.redis_app, DbApp
            ):
                logger.debug(
                    f"Reading redis connection details from: {self.args.redis_app.name}"
                )
                if redis_password is None:
                    redis_password = self.args.redis_app.get_db_password()
                if redis_schema is None:
                    redis_schema = self.args.redis_app.get_db_schema() or "0"
                if redis_host is None:
                    redis_host = self.args.redis_app.get_db_host_k8s()
                if redis_port is None:
                    redis_port = self.args.redis_app.get_db_port_k8s()
                if redis_driver is None:
                    redis_driver = self.args.redis_app.get_db_driver()

            # Set the AIRFLOW__CELERY__RESULT_BACKEND
            celery_broker_url = f"{redis_driver}://{redis_password}{redis_host}:{redis_port}/{redis_schema}"
            if "None" not in celery_broker_url:
                container_env["AIRFLOW__CELERY__BROKER_URL"] = celery_broker_url

            # Set the redis connection details
            if redis_password is not None:
                container_env["REDIS_PASSWORD"] = redis_password
            if redis_schema is not None:
                container_env["REDIS_SCHEMA"] = redis_schema
            if redis_host is not None:
                container_env["REDIS_HOST"] = redis_host
            if redis_port is not None:
                container_env["REDIS_PORT"] = str(redis_port)

        # Update the container env using env_file
        env_data_from_file = self.get_env_data_from_file()
        if env_data_from_file is not None:
            container_env.update(env_data_from_file)

        # Update the container env with user provided env
        if self.args.env is not None and isinstance(self.args.env, dict):
            container_env.update(self.args.env)

        # Create a ConfigMap to set the container env variables which are not Secret
        container_env_cm = CreateConfigMap(
            cm_name=self.args.config_map_name or get_default_configmap_name(app_name),
            app_name=app_name,
            data=container_env,
        )
        # logger.debug(f"ConfigMap {container_env_cm.cm_name}: {container_env_cm.json(indent=2)}")
        config_maps.append(container_env_cm)

        # Create a Secret to set the container env variables which are Secret
        secret_data_from_file = self.get_secret_data_from_file()
        if secret_data_from_file is not None:
            container_env_secret = CreateSecret(
                secret_name=self.args.secret_name or get_default_secret_name(app_name),
                app_name=app_name,
                string_data=secret_data_from_file,
            )
            secrets.append(container_env_secret)

        # If mount_workspace=True first check if the workspace
        # should be mounted locally, otherwise
        # Create a Sidecar git-sync container and volume
        if self.args.mount_workspace:
            workspace_volume_name = (
                self.args.workspace_volume_name or get_default_volume_name(app_name)
            )

            if self.args.k8s_mount_local_workspace:
                workspace_root_path_str = str(self.workspace_root_path)
                workspace_root_container_path_str = str(workspace_root_container_path)
                logger.debug(f"Mounting: {workspace_root_path_str}")
                logger.debug(f"\tto: {workspace_root_container_path_str}")
                workspace_volume = CreateVolume(
                    volume_name=workspace_volume_name,
                    app_name=app_name,
                    mount_path=workspace_root_container_path_str,
                    volume_type=VolumeType.HOST_PATH,
                    host_path=HostPathVolumeSource(
                        path=workspace_root_path_str,
                    ),
                )
                volumes.append(workspace_volume)

            elif self.args.create_git_sync_sidecar:
                workspace_parent_container_path_str = str(
                    self.args.workspace_parent_container_path
                )
                logger.debug(f"Creating EmptyDir")
                logger.debug(f"\tat: {workspace_parent_container_path_str}")
                workspace_volume = CreateVolume(
                    volume_name=workspace_volume_name,
                    app_name=app_name,
                    mount_path=workspace_parent_container_path_str,
                    volume_type=VolumeType.EMPTY_DIR,
                )
                volumes.append(workspace_volume)

                if self.args.git_sync_repo is None:
                    print_error("git_sync_repo invalid")
                else:
                    git_sync_env = {
                        "GIT_SYNC_REPO": self.args.git_sync_repo,
                        "GIT_SYNC_ROOT": str(self.args.workspace_parent_container_path),
                        "GIT_SYNC_DEST": workspace_name,
                    }
                    if self.args.git_sync_branch is not None:
                        git_sync_env["GIT_SYNC_BRANCH"] = self.args.git_sync_branch
                    if self.args.git_sync_wait is not None:
                        git_sync_env["GIT_SYNC_WAIT"] = str(self.args.git_sync_wait)
                    git_sync_sidecar = CreateContainer(
                        container_name="git-sync-workspaces",
                        app_name=app_name,
                        image_name="k8s.gcr.io/git-sync",
                        image_tag="v3.1.1",
                        env=git_sync_env,
                        envs_from_configmap=[cm.cm_name for cm in config_maps]
                        if len(config_maps) > 0
                        else None,
                        envs_from_secret=[secret.secret_name for secret in secrets]
                        if len(secrets) > 0
                        else None,
                        volumes=[workspace_volume],
                    )
                    containers.append(git_sync_sidecar)

        # Create the ports to open
        # if open_container_port = True
        if self.args.open_container_port:
            container_port = CreatePort(
                name=self.args.container_port_name,
                container_port=self.args.container_port,
            )
            ports.append(container_port)

        # if open_app_port = True
        # 1. Set the app_port in the container env
        # 2. Open the superset app port
        app_port: Optional[CreatePort] = None
        if self.args.open_app_port:
            # Set the app port in the container env
            if container_env_cm.data is not None:
                container_env_cm.data["AIRFLOW__WEBSERVER__WEB_SERVER_PORT"] = str(
                    self.args.app_port
                )
            # Open the port
            app_port = CreatePort(
                name=self.args.app_port_name,
                container_port=self.args.app_port,
                service_port=self.get_app_service_port(),
                node_port=self.args.app_node_port,
                target_port=self.args.app_target_port or self.args.app_port_name,
            )
            ports.append(app_port)

        # if open_worker_log_port = True
        # 1. Set the worker_log_port in the container env
        # 2. Open the worker_log_port
        if self.args.open_worker_log_port:
            # Set the worker_log_port in the container_env
            if container_env_cm.data is not None:
                container_env_cm.data["AIRFLOW__LOGGING__WORKER_LOG_SERVER_PORT"] = str(
                    self.args.worker_log_port
                )
            # Open the port
            worker_log_port = CreatePort(
                name=self.args.worker_log_port_name,
                container_port=self.args.worker_log_port,
            )
            ports.append(worker_log_port)

        # if open_flower_port = True
        # 1. Set the flower_port in the container env
        # 2. Open the flower_port
        flower_port: Optional[CreatePort] = None
        if self.args.open_flower_port:
            # Set the flower_port in the container_env
            if container_env_cm.data is not None:
                container_env_cm.data["AIRFLOW__CELERY__FLOWER_PORT"] = str(
                    self.args.flower_port
                )
            # Open the port
            flower_port = CreatePort(
                name=self.args.flower_port_name,
                container_port=self.args.flower_port,
                service_port=self.get_flower_service_port(),
                target_port=self.args.flower_target_port or self.args.flower_port_name,
            )
            ports.append(flower_port)

        container_labels: Optional[Dict[str, Any]] = self.args.container_labels
        if k8s_build_context.labels is not None:
            if container_labels:
                container_labels.update(k8s_build_context.labels)
            else:
                container_labels = k8s_build_context.labels
        # Create the container
        k8s_container = CreateContainer(
            container_name=self.get_container_name(),
            app_name=app_name,
            image_name=self.args.image_name,
            image_tag=self.args.image_tag,
            # Equivalent to docker images CMD
            args=[self.args.command]
            if isinstance(self.args.command, str)
            else self.args.command,
            # Equivalent to docker images ENTRYPOINT
            command=self.args.entrypoint,
            image_pull_policy=self.args.image_pull_policy,
            envs_from_configmap=[cm.cm_name for cm in config_maps]
            if len(config_maps) > 0
            else None,
            envs_from_secret=[secret.secret_name for secret in secrets]
            if len(secrets) > 0
            else None,
            ports=ports if len(ports) > 0 else None,
            volumes=volumes if len(volumes) > 0 else None,
            labels=container_labels,
        )
        containers.append(k8s_container)

        # Set default container for kubectl commands
        # https://kubernetes.io/docs/reference/labels-annotations-taints/#kubectl-kubernetes-io-default-container
        pod_annotations = {
            "kubectl.kubernetes.io/default-container": k8s_container.container_name
        }

        deploy_labels: Optional[Dict[str, Any]] = self.args.deploy_labels
        if k8s_build_context.labels is not None:
            if deploy_labels:
                deploy_labels.update(k8s_build_context.labels)
            else:
                deploy_labels = k8s_build_context.labels
        # Create the deployment
        k8s_deployment = CreateDeployment(
            replicas=self.args.replicas,
            deploy_name=self.args.deploy_name or get_default_deploy_name(app_name),
            pod_name=self.args.pod_name or get_default_pod_name(app_name),
            app_name=app_name,
            namespace=k8s_build_context.namespace,
            service_account_name=k8s_build_context.service_account_name,
            containers=containers if len(containers) > 0 else None,
            pod_node_selector=self.args.pod_node_selector,
            restart_policy=self.args.restart_policy,
            termination_grace_period_seconds=self.args.termination_grace_period_seconds,
            volumes=volumes if len(volumes) > 0 else None,
            labels=deploy_labels,
            pod_annotations=pod_annotations,
            topology_spread_key=self.args.topology_spread_key,
            topology_spread_max_skew=self.args.topology_spread_max_skew,
            topology_spread_when_unsatisfiable=self.args.topology_spread_when_unsatisfiable,
        )

        # Create the services
        if self.args.create_app_service:
            app_service_labels: Optional[Dict[str, Any]] = self.args.app_service_labels
            if k8s_build_context.labels is not None:
                if app_service_labels:
                    app_service_labels.update(k8s_build_context.labels)
                else:
                    app_service_labels = k8s_build_context.labels
            app_service = CreateService(
                service_name=self.get_app_service_name(),
                app_name=app_name,
                namespace=k8s_build_context.namespace,
                service_account_name=k8s_build_context.service_account_name,
                service_type=self.args.app_service_type,
                deployment=k8s_deployment,
                ports=[app_port] if app_port else None,
                labels=app_service_labels,
            )
            services.append(app_service)

        if self.args.create_flower_service:
            flower_service_labels: Optional[
                Dict[str, Any]
            ] = self.args.flower_service_labels
            if k8s_build_context.labels is not None:
                if flower_service_labels:
                    flower_service_labels.update(k8s_build_context.labels)
                else:
                    flower_service_labels = k8s_build_context.labels
            flower_service = CreateService(
                service_name=self.get_flower_service_name(),
                app_name=app_name,
                namespace=k8s_build_context.namespace,
                service_account_name=k8s_build_context.service_account_name,
                service_type=self.args.flower_service_type,
                deployment=k8s_deployment,
                ports=[flower_port] if flower_port else None,
                labels=flower_service_labels,
            )
            services.append(flower_service)

        # Create the K8sResourceGroup
        k8s_resource_group = CreateK8sResourceGroup(
            name=app_name,
            enabled=self.args.enabled,
            config_maps=config_maps if len(config_maps) > 0 else None,
            secrets=secrets if len(secrets) > 0 else None,
            services=services if len(services) > 0 else None,
            deployments=[k8s_deployment],
        )

        return k8s_resource_group.create()

    def init_k8s_resource_groups(self, k8s_build_context: K8sBuildContext) -> None:
        k8s_rg = self.get_k8s_rg(k8s_build_context)
        if k8s_rg is not None:
            if self.k8s_resource_groups is None:
                self.k8s_resource_groups = OrderedDict()
            self.k8s_resource_groups[k8s_rg.name] = k8s_rg
