# Infrastructure Blueprint: Isolated Network Architecture via Rootless Podman

**Target Testing Subnet:** Automatically assigned by Podman; separate from the production cluster network.
**Execution Environment:** Podman v4.5+ (Rootless Configuration Space)

---

## 1. Technical Provisioning Overview
Rootless Podman uses a specialized helper system called **`slirp4netns`** or **`pasta`** to translate unprivileged user space network calls into valid host system requests. By default, Podman spins up containers inside a standard generic `10.88.0.0/16` bridge network.

Create a named Podman network and let Podman assign a private subnet that does not reuse the production cluster range.

```text
+-----------------------------------------------------------------------------------+
| RIPPING HOST SYSTEM (User Space Environment) |
| |
| [Rootless Podman Runtime] |
| │ |
| └──> [Virtual Bridge Driver: cluster-isolated-net] |
| │ (Podman-managed private subnet) |
| │ |
| ├──> [Container 1: rabbitmq-test] |
| └──> [Container 2: worker-test]   |
+-----------------------------------------------------------------------------------+
```

---

## 2. Isolated Network Provisioning Steps

### Step 1: Initialize the Podman Test Network
Create the isolated network; Podman selects its subnet and gateway:

```bash
podman network create \
  --driver bridge \
  cluster-isolated-net
```

### Step 2: Inspect the Test Network

Inspect the assigned network details:
```bash
podman network inspect cluster-isolated-net
```

Inspect the output to confirm Podman assigned a subnet and gateway for this network. The values will depend on the local Podman configuration:
```json
[
     {
          "name": "cluster-isolated-net",
          "id": "a1b2c3d4e5f6...",
          "driver": "bridge",
          "network_interface": "<Podman-created-interface>",
          "subnets": [
               {
                    "subnet": "<Podman-assigned-subnet>",
                    "gateway": "<Podman-assigned-gateway>"
               }
          ],
          "ipv6_enabled": false,
          "internal": false,
          "dns_enabled": true
     }
]
```

---

## 3. Multi-Container Local Test Script

To verify the network setup, this routine boots RabbitMQ and a HandBrake CLI instance on the isolated Podman network. Podman assigns each container an address automatically.

Save this script layer as `test_local_cluster.sh`, make it executable (`chmod +x test_local_cluster.sh`), and run it:

```bash
#!/bin/bash
set -e

echo "[1/3] Spinning up containerized RabbitMQ Server on custom network..."
podman run -d \
  --name rabbitmq-test \
  --network cluster-isolated-net \
  -e RABBITMQ_DEFAULT_USER=guest \
  -e RABBITMQ_DEFAULT_PASS=guest \
  -p 5672:5672 \
  -p 15672:15672 \
  docker.io/library/rabbitmq:3.13-management-alpine

echo "[2/3] Waiting for RabbitMQ storage structures to settle inside network..."
sleep 10

echo "[3/3] Deploying HandBrake worker instance on the test network..."
# Connects to RabbitMQ by its container name on the Podman network
podman run --rm \
  --name worker-test \
  --network cluster-isolated-net \
     -e RABBITMQ_HOST=rabbitmq-test \
  localhost/handbrake-worker:latest --version

echo "========================================================================="
echo "[SUCCESS] Local Podman network communication verified."
echo "RabbitMQ Management UI is reachable at: http://localhost:15672"
echo "========================================================================="
```

---

## 4. Environment Teardown

Once your local pipeline testing cycles are finished, wipe the transient containers and tear down the virtual testing network using these commands:

```bash
# Force remove the testing container workloads
podman rm -f rabbitmq-test

# Wipe the network bridge allocation configuration from the user profile space
podman network rm cluster-isolated-net
```
