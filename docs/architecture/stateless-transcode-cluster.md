# Comprehensive System Manual: Stateless Distributed Transcoding Cluster

- **Platform:** Raspberry Pi 5 cluster (6-7 nodes)
- **Operating system:** Talos Linux (stateless PXE boot)
- **Storage:** M.2 NVMe and NFS NAS mounts
- **Orchestration:** Kubernetes, RabbitMQ, and KEDA

---

## 1. Technical Architecture Specification
This implementation uses a completely decoupled ingest, asynchronous queue, and dynamic computing framework. The cluster operates statelessly, minimizing hardware wearing and mitigating single-point-of-failure vulnerabilities.


```text
+------------------+ Lossless Ripping (MKV/ISO) +-------------------------+
| Ingest Device | ─────────────────────────────────────> | NAS Storage Array |
+------------------+ | (NFS Shared Directory) |
+-------------------------+
│
│ Kernel File Watcher
▼
+------------------+ Publish Job Metadata Packet +-------------------------+
| RabbitMQ Broker | <───────────────────────────────────── | Python Ingest Daemon |
+------------------+ +-------------------------+
│ ▲
│ Monitor │ Dynamic Scaling Hook (0 to 7 Replicas)
▼ │
+-------------------------------------------------------------------------------------+
| Talos Linux Kubernetes Cluster Infrastructure (RAM Engine) |
| |
| +-----------------+ Container Engine Cache +----------------------------------+ |
| | Kubelet / Pods | ──────────────────────> | Local Combo NVMe Target | |
| +-----------------+ | /var/lib/containerd | |
| │ +----------------------------------+ |
| │ Parallel Read/Write Streams |
| ▼ |
| +-------------------------------------------------------------------------------+ |
| | HandBrakeCLI Headless Worker Sub-System (ARM64 Optimized Processing Pods) | |
| +-------------------------------------------------------------------------------+ |
+-------------------------------------------------------------------------------------+
```


### 1.1 Structural Operational Data Lifecycle
1. **Extraction Ingest:** Physical media is extracted directly to a highly resilient network storage tier utilizing a central NAS node (e.g., TrueNAS / Custom Linux Array) via low-overhead NFS mounting shares.
2. **System Messaging Dispatch:** The specialized automation daemon intercepts the completed file system file locks, transforms paths into container-relocated destination keys, and ships an operation contract to a persistent RabbitMQ broker.
3. **Reactive Pod Scaling:** KEDA scales the worker configuration dynamically based on execution depth. If the target message queue contains elements, the cluster replica requirements transition instantly from `0` to `7` nodes.
4. **Execution Processing:** The headless `HandBrakeCLI` pods initialize inside the volatile system RAM of the Raspberry Pi 5. The nodes handle video frame sequences entirely through multi-threaded software algorithms (`x264`/`x265`), optimizing the enhanced Cortex-A76 core matrix before dumping output records straight onto the network storage tier.

---

## 2. Hardware Stack Configuration Matrix

### 2.1 The Raspberry Pi 5 BCM2712 Silo Paradigm
The structural architecture of the Broadcom BCM2712 system-on-chip running inside the Raspberry Pi 5 **does not feature specialized hardware-accelerated H.264 or H.265 encoding blocks**. Multimedia encoding engines were excluded from the silicon die layer during engineering to prioritize CPU core performance densities.

Because the Cortex-A76 core architecture delivers a 2.5× to 3× performance acceleration factor per clock layer compared to the Pi 4, running distributed software transcoding engines across 6 to 7 physical nodes produces higher compression ratios, cleaner visual profiles, and reduced disk footprints when evaluated against legacy hardware video encoders.

### 2.2 Integrated Combo Expansion Boards
The cluster utilizes all-in-one execution hats combining **IEEE 802.3at (PoE+)** active conversion circuit loops directly alongside a dedicated **PCIe M.2 M-Key NVMe** data slot.

*   **Thermal Mitigation:** Continuous multi-core CPU software decoding pins processing pipelines at full capacity. Combo boards must feature open-access frame cutouts allowing physical attachment of the official Raspberry Pi active cooler assembly or feature an integrated hat cooling fan providing at least 3.5 CFM airflow.
*   **Power Loading Thresholds:** The operational variance window of an active Pi 5 SoC under heavy software transcoding combined with active PCIe NVMe controller operations swings between 14W and 18W. The network managed PoE switch fabric must guarantee an overhead ceiling profile of **25.5W per physical port** matching the PoE+ execution parameter guidelines.

---

## 3. Netboot (PXE) and In-Memory Configuration Steps

Talos Linux runs as a fully immutable system directly within volatile system memory (RAM). Standard system partitions are entirely absent from physical cluster disks during the initial startup sequence.

### 3.1 SPI EEPROM Modification Procedure
Each individual Raspberry Pi 5 node must be initialized within a temporary operating environment exactly once to flash the required parameters to the non-volatile system bootloader EEPROM.

1. Generate a basic **Raspberry Pi OS Lite (64-bit)** image layout onto an execution MicroSD media drive.
2. Insert the flash card into the target board, interface the node with your physical local network segment, and power the device up.
3. Establish a standard network secure shell (SSH) session or interact with the unit using direct peripheral consoles.
4. Open the native bootloader configuration subsystem file script by running:
   ```bash
   sudo rpi-eeprom-config --edit
   ```
5. Modify the file structure logic to mirror the hardware variables outlined below:
   ```ini
   [all]
    BOOT_ORDER=0xf162
    TFTP_PREFIX=0
   PCIE_PROBE=1
   ```
    * `BOOT_ORDER=0xf162` tries network boot, then NVMe, then SD before restarting the sequence.
    * `TFTP_PREFIX=0` uses the Raspberry Pi serial number as the TFTP directory prefix.
6. Commit the file to storage and exit the console script wrapper (`Ctrl+O`, `Enter`, `Ctrl+X`).
7. Write the modification records directly into the physical SPI EEPROM component:
   ```bash
   sudo rpi-eeprom-update -d -a
   ```
8. Terminate system electricity, extract the MicroSD media drive, and loop through these configuration steps for the remaining nodes in the pool.

### 3.2 Network Server Provisioning Architecture
Configure your central utility server or local gateway infrastructure to serve network boot resources using the structural templates provided.

#### Dnsmasq Integration Profile Configuration (`dnsmasq.conf`)

Use the gateway's authoritative DHCP/TFTP configuration in [routing setup](../cluster-setup/routing-setup.md). It binds to `192.168.45.1` and leases only from `192.168.45.50` through `192.168.45.99`.

#### TFTP Files and `cmdline.txt`

Populate the TFTP root with the boot files produced by the selected Raspberry Pi/Talos boot chain. With `TFTP_PREFIX=0`, each Pi uses its serial number as its TFTP directory prefix. The exact filenames and command-line syntax have not been verified for this cluster, so do not use the former `vmlinuz-arm64`/`initramfs-arm64.xz` placeholders.

The per-node command line must set `talos.config` to the matching gateway URL, for example `http://192.168.45.1/talos-configs/controlplane.yaml` or `http://192.168.45.1/talos-configs/worker-01.yaml`.

---

## 4. Storage Architecture and Resource Boundaries

Because the system engine executes fully within a RAM environment, the high-speed combo NVMe flash drive is isolated from basic OS operations. It serves as dedicated cluster data and caching storage.

### 4.1 Talos Persistence Configuration Snippet
Embed these structural paths inside your generated `controlplane.yaml` and `worker.yaml` files before node instantiation:

```yaml
machine:
  storage:
    disks:
      - device: /dev/nvme0n1
        partitions:
          - mountpoint: /var/lib/containerd
          - mountpoint: /var/lib/kubelet
          - mountpoint: /var/mnt/storage
```
*   `/var/lib/containerd`: Caches application layers directly to M.2 storage silicon, preventing network traffic congestion when scaling node container deployments.
*   `/var/lib/kubelet`: Routes application logs and transient workspace partitions directly to physical flash storage, saving RAM resources for the primary transcoding pipelines.
*   `/var/mnt/storage`: Creates the dedicated physical volume required to track persistent states for the core database engines.

---

## 5. Kubernetes Manifest Implementation

Execute these blueprints directly against the running cluster control plane using `kubectl apply -f <target_manifest>.yaml` once initialization operations settle.

### 5.1 RabbitMQ Cluster Deployment Configuration (`rabbitmq.yaml`)
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: rabbitmq-system
---
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: nvme-local-storage
provisioner: kubernetes.io/no-provisioner
volumeBindingMode: WaitForFirstConsumer
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: rabbitmq-nvme-pv
spec:
  capacity:
    storage: 50Gi
  volumeMode: Filesystem
  accessModes:
  - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: nvme-local-storage
  local:
    path: /var/mnt/storage/rabbitmq
  nodeAffinity:
    required:
      nodeSelectorTerms:
      - matchExpressions:
        - key: kubernetes.io/hostname
          operator: In
          values:
          - k8s-worker-01
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: rabbitmq-nvme-pvc
  namespace: rabbitmq-system
spec:
  accessModes:
  - ReadWriteOnce
  volumeMode: Filesystem
  resources:
    requests:
      storage: 50Gi
  storageClassName: nvme-local-storage
---
apiVersion: ://rabbitmq.com
kind: RabbitmqCluster
metadata:
  name: transcode-queue-broker
  namespace: rabbitmq-system
spec:
  replicas: 1
  persistence:
    storageClassName: nvme-local-storage
    storage: 50Gi
```

### 5.2 Dynamic Transcoding Deployment & Scaling Rules (`transcoder-keda.yaml`)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: handbrake-cluster-worker
  namespace: rabbitmq-system
  labels:
    app: handbrake-worker
spec:
  replicas: 0 # Orchestration handled completely by KEDA execution configurations

## selector:
matchLabels:
app: handbrake-worker
template:
metadata:
labels:
app: handbrake-worker
spec:
containers:
- name: handbrake-runner
image: davidmatthews/handbrake-cli:latest
imagePullPolicy: IfNotPresent
resources:
limits:
cpu: "3500m" # Allocates 3.5 compute units out of 4 to prevent processing engine thread death
memory: "3Gi"
requests:
cpu: "1000m"
memory: "1Gi"
env:
- name: RABBITMQ_HOST
value: "transcode-queue-broker.rabbitmq-system.svc.cluster.local"
volumeMounts:
- name: nas-video-storage
mountPath: /media/videos
volumes:
- name: nas-video-storage
persistentVolumeClaim:
claimName: nfs-video-pvc
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
name: handbrake-keda-scaler
namespace: rabbitmq-system
spec:
scaleTargetRef:
apiVersion: apps/v1
kind: Deployment
name: handbrake-cluster-worker
minReplicaCount: 0 # Forces scale down to zero compute units when queue tracks are fully cleared
maxReplicaCount: 7 # Maximum cluster replication ceiling matching your nodes
cooldownPeriod: 300
pollingInterval: 15
triggers:

* type: rabbitmq
metadata:
queueName: transcode_jobs
queueLength: "1"
host: amqp://guest:guest@transcode-queue-broker.rabbitmq-system.svc.cluster.local:5672/%2f
```

------------------------------
## 6. Automation Pipeline Daemon
Run this operational daemon as a standard background handler directly inside your storage array or automation server ecosystem. It coordinates core tasks by intercepting local storage writes and passing instructions to the cluster infrastructure.

The host-side producer endpoint assumes the AMQP NodePort described in [RabbitMQ setup](../services/rabbitmq-setup.md). The RabbitMQ Operator example in this manual does not itself define that external service.
Initialize tracking engine bindings by installing the required script plugins:
bash pip install pika watchdog 
## Ingestion Dispatch Daemon (watchdog_producer.py)
```python
#!/usr/bin/env python3
import time
import json
import os
import pika
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
## --- INFRASTRUCTURE SETTINGS ---
RABBITMQ_HOST = "192.168.45.11" # RabbitMQ NodePort on a cluster node
QUEUE_NAME = "transcode_jobs"
WATCH_DIRECTORY = "/mnt/nas/media/raw_rips"
OUTPUT_DIRECTORY = "/mnt/nas/media/transcoded_library"
class VideoIngestHandler(FileSystemEventHandler):
def on_closed(self, event):
"""
Intercepts file events explicitly mapped to closure operations.
Ensures script parsing triggers only when file copying steps finish completely.
"""
if event.is_directory:
return
file_path = event.src_path
filename = os.path.basename(file_path)
# Explicitly ignore files not matching raw source files
if not filename.lower().endswith(('.mkv', '.iso')):
return
print(f"[WATCHDOG] Completed file ingestion detected: {filename}. Processing metadata mappings...")
# Match output variables to destination maps mounted within the pod runtime namespace
container_input = os.path.join("/media/videos/raw_rips", filename)
container_output = os.path.join("/media/videos/transcoded_library", os.path.splitext(filename)[0] + ".mp4")
payload = {
"input_file": container_input,
"output_name": container_output
}
self.publish_to_queue(payload)
def publish_to_queue(self, payload_data):
try:
# Open persistent pipes connecting to the cluster infrastructure
connection = pika.BlockingConnection(pika.ConnectionParameters(
host=RABBITMQ_HOST,
port=30072,
heartbeat=600,
blocked_connection_timeout=300
))
channel = connection.channel()
# Affirm queue settings match durable targets to maintain state across cluster changes
channel.queue_declare(queue=QUEUE_NAME, durable=True)
message_body = json.dumps(payload_data)
# Route operational record payload to RabbitMQ queue
channel.basic_publish(
exchange='',
routing_key=QUEUE_NAME,
body=message_body,
properties=pika.BasicProperties(
delivery_mode=2, # Forces physical persistence to protected storage layers
content_type='application/json'
)
)
print(f"[RABBITMQ] Task metadata dispatched to cluster broker: {message_body}")
connection.close()
except Exception as e:
print(f"[CONNECTION EXCEPTION] Pipeline failed to reach broker instance: {str(e)}")
if name == "main":
if not os.path.exists(WATCH_DIRECTORY):
os.makedirs(WATCH_DIRECTORY)
event_handler = VideoIngestHandler()
observer = Observer()
observer.schedule(event_handler, path=WATCH_DIRECTORY, recursive=False)
print(f"[DAEMON STARTED] Monitoring ingest path: '{WATCH_DIRECTORY}'...")
observer.start()
try:
while True:
time.sleep(1)
except KeyboardInterrupt:
print("[DAEMON INTERRUPTED] Shutting down file tracking loops...")
observer.stop()
observer.join()
```
