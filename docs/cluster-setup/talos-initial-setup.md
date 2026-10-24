# Engineering Blueprint: Talos Linux Core Machine Configuration

**Isolated Cluster Domain:** `192.168.45.0/24`
**Gateway host:** `192.168.45.1`
**Control Plane Cluster VIP:** `192.168.45.10`  
**Target Hardware Core:** Raspberry Pi 5 + Integrated Combo M.2/PoE+ HATs  
---
## 1. Control Plane Node Specification (`controlplane.yaml`)

This configuration dictates the behavior of the control-plane node (`192.168.45.10`). Its default route uses the gateway host at `192.168.45.1`. Replace the example interface name `eth0` with the wired NIC name reported by Talos on each Pi.

Save this manifest chunk as your base configuration target for the master node.
```yaml
version: v1alpha1
kind: MachineConfig
machine:
  type: controlplane
  token: unique-cluster-bootstrap-token-here
  ca:
    crt: base64-encoded-ca-certificate-string-here
    key: base64-encoded-ca-private-key-string-here
  network:
    hostname: k8s-master-01
    interfaces:
      - interface: eth0
        dhcp: false
        addresses:
          - 192.168.45.10/24 # Static IP assigned to the master node
        routes:
          - network: 0.0.0.0/0
            gateway: 192.168.45.1 # Gateway host cluster-side address
    nameservers:
      - 1.1.1.1
      - 8.8.8.8
  storage:
    disks:
      - device: /dev/nvme0n1
        partitions:
          - mountpoint: /var/lib/containerd # Redirects container runtimes to NVMe flash
          - mountpoint: /var/lib/kubelet     # Maps local pod storage volumes to NVMe flash
          - mountpoint: /var/mnt/storage     # Storage path target for the RabbitMQ engine
cluster:
  controlPlane:
    endpoint: https://192.168.45.10:6443
  network:
    dnsDomain: cluster.local
    podSubnet: 10.244.0.0/16
    serviceSubnet: 10.96.0.0/12
  token: cluster-token-value-here
  ca:
    crt: cluster-ca-crt-here
    key: cluster-ca-key-here
```
---
## 2. Compute Worker Template (`worker.yaml`)

This template provisions your remaining 6 Raspberry Pi 5 transcoding compute engines. When applying this payload, increment the `hostname` string and the static `addresses` element sequentially (`.11`, `.12`, `.13`, up to `.16`) per physical device. Replace `eth0` with the wired NIC name reported by Talos if it differs.
```yaml
version: v1alpha1
kind: MachineConfig
machine:
  type: worker
  token: unique-cluster-bootstrap-token-here
  ca:
    crt: base64-encoded-ca-certificate-string-here
    key: base64-encoded-ca-private-key-string-here
  network:
    hostname: k8s-worker-01 # Modify sequentially (k8s-worker-02, etc.) per node
    interfaces:
      - interface: eth0
        dhcp: false
        addresses:
          - 192.168.45.11/24 # Modify sequentially (.12, .13, .14, etc.) per node
        routes:
          - network: 0.0.0.0/0
            gateway: 192.168.45.1 # Gateway host cluster-side address
    nameservers:
      - 1.1.1.1
      - 8.8.8.8
  storage:
    disks:
      - device: /dev/nvme0n1
        partitions:
          - mountpoint: /var/lib/containerd # Caches container layers onto NVMe flash storage
          - mountpoint: /var/lib/kubelet     # Puts ephemeral pod scratchpads onto NVMe flash
          - mountpoint: /var/mnt/storage     # Dedicated NVMe path backing the cluster queue
cluster:
  controlPlane:
    endpoint: https://192.168.45.10:6443
  token: cluster-token-value-here
  ca:
    crt: cluster-ca-crt-here
    key: cluster-ca-key-here
```

## 3. Provisioning and Deployment Workflow

Run these steps from the ripping host or an administration workstation.

### Step 1: Install the Talos CLI

Install `talosctl` on the Fedora 44 gateway or another Linux administration host using the [official installer](https://docs.siderolabs.com/talos/getting-started/talosctl):

```bash
curl -sL https://talos.dev/install | sh
command -v talosctl
talosctl version --client
```

The installer supports Linux `amd64` and `arm64`. Use a `talosctl` release matching the Talos version selected for the cluster. To pin a specific release, download the matching binary from the [Talos releases](https://github.com/siderolabs/talos/releases) page instead of relying on the latest installer result.
### Step 2: Generate the Cluster Configuration

Generate the certificates and baseline configuration files:

```bash
talosctl gen config video-transcode-cluster https://192.168.45.10:6443 --output-dir ./cluster-configs
```
- `controlplane.yaml` for the control-plane node.
- `worker.yaml` for worker nodes.
- `talosconfig` for administrative access.

### Step 3: Apply Storage and Network Settings

Edit `controlplane.yaml`. Copy the generated `worker.yaml` once per worker, then set a unique hostname and static address from `.11` through `.16`; save the files as `worker-01.yaml` through `worker-06.yaml`.

### Step 4: Host the Machine Configurations

Copy the customized configuration files to `/srv/www/talos-configs` on the Fedora gateway. Nginx serves this directory at `http://192.168.45.1/talos-configs/`:

First transfer the generated and per-node-customized files to the gateway. Run these install commands on the gateway, assuming the files are in `./cluster-configs` there:

```bash
sudo install -d -o root -g nginx -m 0750 /srv/www/talos-configs
sudo install -o root -g nginx -m 0640 ./cluster-configs/controlplane.yaml /srv/www/talos-configs/controlplane.yaml
sudo install -o root -g nginx -m 0640 ./cluster-configs/worker-01.yaml /srv/www/talos-configs/worker-01.yaml
```

Repeat the worker install for `worker-02.yaml` through `worker-06.yaml`. Set each node's TFTP `cmdline.txt` to its matching URL, for example `talos.config=http://192.168.45.1/talos-configs/worker-01.yaml`.
### Step 5: Boot the Nodes and Bootstrap the Cluster

1. Power on the PoE switch ports for the cluster nodes.
2. Allow the nodes to boot via PXE and retrieve their Talos configurations.
3. When the control plane is ready, configure the CLI and bootstrap the cluster:
   ```bash
   talosctl --talosconfig ./cluster-configs/talosconfig config endpoint 192.168.45.10
   talosctl --talosconfig ./cluster-configs/talosconfig config node 192.168.45.10
   talosctl bootstrap
   ```

Talos will automatically provision the control plane, wipe and format the NVMe drives out-of-band across your fleet to set up caching mounts, and join the worker engines to the pool.


