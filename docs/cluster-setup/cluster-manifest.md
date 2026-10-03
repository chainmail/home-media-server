# Cluster Implementation Manifest: Distributed Transcoding Setup

**Architecture Framework:** Raspberry Pi 5 Stack (6-7 Nodes)
**Base Operating System:** Talos Linux (Stateless PXE Boot Engine)  
**Storage Engine Target:** Local M.2 NVMe + Remote NFS NAS Mounts

---

## 1. EEPROM Firmware Configuration Steps

Configure each Raspberry Pi 5 node before assembling the cluster:

1. Flash a standard **Raspberry Pi OS Lite (64-bit)** image onto a temporary MicroSD card.
2. Insert the card into the Pi 5, connect the node to your network, and power it on.
3. Connect over SSH or attach a keyboard and monitor.
4. Open the EEPROM configuration editor:

  ```bash
  sudo rpi-eeprom-config --edit
  ```

5. Set the boot parameters:

  ```ini
  [all]
  BOOT_ORDER=0xf162
  TFTP_PREFIX=0
  PCIE_PROBE=1
  ```

6. Save and exit the editor (`Ctrl+O`, `Enter`, `Ctrl+X`).
7. Update the EEPROM:

  ```bash
  sudo rpi-eeprom-update -d -a
  ```

8. Power down the node, remove the MicroSD card, and repeat for the remaining nodes.

---

## 2. Infrastructure Server Network Staging Templates
The network deployment infrastructure requires a helper instance (e.g., a central Linux utility server or TrueNAS server) running a combined DHCP/TFTP service alongside a lightweight HTTP asset manager.

### 2.1 Dnsmasq Configuration

Use the gateway-only DHCP/TFTP configuration in [routing-setup.md](routing-setup.md) as the source of truth. It binds services to `192.168.45.1` and keeps dynamic leases outside the static node range.

### 2.2 TFTP Files and `cmdline.txt`

Populate `/var/lib/tftpboot` with the files required by the selected Raspberry Pi/Talos boot chain. Since `TFTP_PREFIX=0`, each Pi uses its serial number as its TFTP directory prefix. The exact file list and command-line syntax remain to be verified; do not deploy the earlier placeholder kernel/initramfs filenames.

Each node's `cmdline.txt` must point to its own Nginx-served machine configuration, for example `http://192.168.45.1/talos-configs/controlplane.yaml` or `http://192.168.45.1/talos-configs/worker-01.yaml`.

---

## 3. Talos Linux Local Storage Allocation Settings
Because the operating system workspace initializes purely within volatile RAM boundaries, the local NVMe drive attached to your combo board must be explicitly partitioned out-of-band by Talos to support local Kubernetes storage persistence.

Include these exact block definitions inside your generated `controlplane.yaml` and `worker.yaml` deployment manifests:
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
- `/var/lib/containerd`: Caches container image layers on NVMe storage.
- `/var/lib/kubelet`: Stores ephemeral Kubernetes data on NVMe storage.
- `/var/mnt/storage`: Intended for persistent RabbitMQ state.

---

## 4. Kubernetes Infrastructure Workload Definitions
Deploy these manifests into the cluster using `kubectl apply -f <filename>.yaml` once the Talos control plane has initialized successfully.

### 4.1 RabbitMQ Cluster Operator Infrastructure (`rabbitmq.yaml`)

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

### 4.2 Automated Transcoding Deployment & KEDA Rules (`transcoder-keda.yaml`)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: handbrake-cluster-worker
  namespace: rabbitmq-system
  labels:
    app: handbrake-worker
spec:
  replicas: 0 # KEDA dynamically manages this replication value between 0 and 7
  selector:
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
            cpu: "3500m" # Allocates 3.5 out of 4 processing cores to prevent system execution lockups
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
---
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
  minReplicaCount: 0  # Scales to zero when no raw media files are pending processing
  maxReplicaCount: 7  # Maximum cluster concurrency matching physical hardware node constraints
  cooldownPeriod: 300
  pollingInterval: 15
  triggers:
  - type: rabbitmq
    metadata:
      queueName: transcode_jobs
      queueLength: "1"
      host: amqp://guest:guest@transcode-queue-broker.rabbitmq-system.svc.cluster.local:5672/%2f
```

---

## 5. Automation Python Producer Script

This script example monitors the ingest directory and publishes tasks through the AMQP NodePort endpoint in [rabbitmq-setup.md](../services/rabbitmq-setup.md). If deploying the RabbitMQ Operator example above instead, configure an externally reachable AMQP service before using this host-side producer.

Install its dependencies on the host:

```bash
pip install pika watchdog
```

### Ingestion Script Code File (`watchdog_producer.py`)
```python
#!/usr/bin/env python3
import time
import json
import os
import pika
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- CONFIGURATION CONSTANTS ---
RABBITMQ_HOST = "192.168.45.11"
QUEUE_NAME = "transcode_jobs"
WATCH_DIRECTORY = "/mnt/nas/media/raw_rips"
OUTPUT_DIRECTORY = "/mnt/nas/media/transcoded_library"

class VideoIngestHandler(FileSystemEventHandler):
    def on_closed(self, event):
        """
        Interceptors capture the standard file system IN_CLOSE_WRITE event state.
        This isolates tracking metrics to completely written files, ignoring partial block streams.
        """
        if event.is_directory:
            return
        file_path = event.src_path
        filename = os.path.basename(file_path)
        
        # Explicit target verification limiters matching raw media extract blocks
        if not filename.lower().endswith(('.mkv', '.iso')):
            return


print(f"[WATCHDOG] Valid raw media format detected: {filename}. Processing system load metadata...")
# Construct path mappings relative to the interior container namespace environment
container_input = os.path.join("/media/videos/raw_rips", filename)
container_output = os.path.join("/media/videos/transcoded_library", os.path.splitext(filename)[0] + ".mp4")
payload = {
"input_file": container_input,
"output_name": container_output
}
self.publish_to_queue(payload)
def publish_to_queue(self, payload_data):
try:
# Build network connection layers targeting the cluster runtime
connection = pika.BlockingConnection(pika.ConnectionParameters(
host=RABBITMQ_HOST,
port=30072,
heartbeat=600,
blocked_connection_timeout=300
))
channel = connection.channel()
# Affirm queue attributes are marked as highly durable to prevent data drops during cluster shifts
channel.queue_declare(queue=QUEUE_NAME, durable=True)
message_body = json.dumps(payload_data)
# Emit execution instruction to RabbitMQ broker
channel.basic_publish(
exchange='',
routing_key=QUEUE_NAME,
body=message_body,
properties=pika.BasicProperties(
delivery_mode=2, # Marks message data explicitly persistent on physical storage
content_type='application/json'
)
)
print(f"[RABBITMQ] Successfully queued transcoding metadata payload: {message_body}")
connection.close()
except Exception as e:
print(f"[CRITICAL ERROR] Message brokerage connection failed to build: {str(e)}")
if name == "main":
if not os.path.exists(WATCH_DIRECTORY):
os.makedirs(WATCH_DIRECTORY)
event_handler = VideoIngestHandler()
observer = Observer()
observer.schedule(event_handler, path=WATCH_DIRECTORY, recursive=False)
print(f"[SYSTEM SERVICE INTIALIZED] Monitoring directory: '{WATCH_DIRECTORY}' for incoming media...")
observer.start()
try:
while True:
time.sleep(1)
except KeyboardInterrupt:
print("[SYSTEM SERVICE TERMINATING] Halting filesystem monitors...")
observer.stop()
observer.join()
```
