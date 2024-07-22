import os
import subprocess
import sys

import click


@click.group(name="cluster")
def cluster():
    """Start, configure and stop a warnet k8s cluster"""


def run_command(command, stream_output=False):
    if stream_output:
        process = subprocess.Popen(
            ["/bin/bash", "-c", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        for line in iter(process.stdout.readline, ""):
            print(line, end="")

        process.stdout.close()
        return_code = process.wait()

        if return_code != 0:
            print(f"Command failed with return code {return_code}")
            return False
        return True
    else:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, executable="/bin/bash"
        )
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return False
        print(result.stdout)
        return True


@cluster.command()
def start():
    """Setup and start the RPC in dev mode with minikube"""
    script_content = """
    #!/usr/bin/env bash
    set -euxo pipefail

    # Function to check if minikube is running
    check_minikube() {
        minikube status | grep -q "Running" && echo "Minikube is already running" || minikube start --memory=max --cpus=max --mount --mount-string="$PWD:/mnt/src"
    }

    # Function to check if warnet-rpc container is already running
    check_warnet_rpc() {
        if kubectl get pods --all-namespaces | grep -q "bitcoindevproject/warnet-rpc"; then
            echo "warnet-rpc already running in minikube"
            exit 1
        fi
    }

    # Check minikube status
    check_minikube

    # Build image in local registry and load into minikube
    docker build -t warnet/dev -f src/warnet/templates/rpc/Dockerfile_rpc_dev . --load
    minikube image load warnet/dev

    # Setup k8s
    kubectl apply -f src/warnet/templates/rpc/namespace.yaml
    kubectl apply -f src/warnet/templates/rpc/rbac-config.yaml
    kubectl apply -f src/warnet/templates/rpc/warnet-rpc-service.yaml
    kubectl apply -f src/warnet/templates/rpc/warnet-rpc-statefulset-dev.yaml
    kubectl config set-context --current --namespace=warnet

    # Check for warnet-rpc container
    check_warnet_rpc

    until kubectl get pod rpc-0 --namespace=warnet; do
       echo "Waiting for server to find pod rpc-0..."
       sleep 4
    done

    echo "⏲️ This could take a minute or so."
    kubectl wait --for=condition=Ready --timeout=2m pod rpc-0

    echo Done...
    """
    res = run_command(script_content, stream_output=True)
    if res:
        _port_start_internal()


@cluster.command()
def stop():
    """Stop the warnet server and tear down the cluster"""
    script_content = """
    #!/usr/bin/env bash
    set -euxo pipefail

    kubectl delete namespace warnet
    kubectl delete namespace warnet-logging
    kubectl config set-context --current --namespace=default

    minikube image rm warnet/dev
    """
    run_command(script_content, stream_output=True)
    _port_stop_internal()


def is_windows():
    return sys.platform.startswith("win")


def run_detached_process(command):
    if is_windows():
        # For Windows, use CREATE_NEW_PROCESS_GROUP and DETACHED_PROCESS
        subprocess.Popen(
            command,
            shell=True,
            stdin=None,
            stdout=None,
            stderr=None,
            close_fds=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
        )
    else:
        # For Unix-like systems, use nohup and redirect output
        command = f"nohup {command} > /dev/null 2>&1 &"
        subprocess.Popen(command, shell=True, stdin=None, stdout=None, stderr=None, close_fds=True)

    print(f"Started detached process: {command}")


def _port_start_internal():
    command = "kubectl port-forward svc/rpc 9276:9276"
    run_detached_process(command)
    print(
        "Port forwarding on port 9276 started in the background. Use 'warcli' (or 'kubectl') to manage the warnet."
    )


@cluster.command()
def port_start():
    """Port forward (runs as a detached process)"""
    _port_start_internal()


def _port_stop_internal():
    if is_windows():
        os.system("taskkill /F /IM kubectl.exe")
    else:
        os.system("pkill -f 'kubectl port-forward svc/rpc 9276:9276'")
    print("Port forwarding stopped.")


@cluster.command()
def port_stop():
    """Stop the port forwarding process"""
    _port_stop_internal()
