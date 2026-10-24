# Infrastructure Manifest: Kubernetes Distributed NFS Storage Bridge

**Isolated Cluster Domain:** `192.168.45.0/24`
**Gateway and NFS host:** `192.168.45.1`
**Target Namespace Framework:** `rabbitmq-system`  
**Storage Protocol Engine:** Network File System (NFSv4)  
## 1. Storage Bridge Specification (`nfs-media-storage.yaml`)

This deployment profile configures the persistent network mapping between your central storage array and your stateless Talos nodes. Because it acts as a shared resource, all 7 containerized HandBrake compute nodes can read raw source frames and write back finalized media tracks simultaneously (`ReadWriteMany`).

The NFS export is served by the gateway at `192.168.45.1` and must allow clients from `192.168.45.0/24`.

Save this block as `nfs-media-storage.yaml` and deploy it with:

```bash
kubectl apply -f nfs-media-storage.yaml
```
```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: nfs-video-pv
  labels:
    storage.type: nas-nfs
spec:
  capacity:
    storage: 2T # Matches the configured NFS export capacity
  volumeMode: Filesystem
  accessModes:
    - ReadWriteMany # Grants concurrent multi-pod computational read/write permissions
  persistentVolumeReclaimPolicy: Retain
  storageClassName: nfs-nas-media
  mountOptions:
    - nfsvers=4.1
    - rsize=1048576 # Optimized 1MB read buffers to maximize streaming throughput
    - wsize=1048576 # Optimized 1MB write buffers for high-density audio/video logs
    - hard
    - timeo=600
    - retrans=2
    - noatime       # Disables access time updates on the NAS to mitigate tracking overhead
  nfs:
    path: /                      # NFSv4 pseudo-root from the gateway export
    server: 192.168.45.1         # Gateway host NFS export
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: nfs-video-pvc
  namespace: rabbitmq-system
spec:
  accessModes:
    - ReadWriteMany
  volumeMode: Filesystem
  resources:
    requests:
      storage: 2T
  storageClassName: nfs-nas-media
  selector:
    matchLabels:
      storage.type: nas-nfs
```

## 2. Production Implementation Validation
To ensure your stateless cluster framework is communicating correctly with your storage layer across the network gateway interface, follow these diagnostics steps after deploying the storage manifests.
### Step 1: Verify Storage Subsystem Bindings

Query the Kubernetes cluster state to verify that the storage assets have reached the `Bound` state:

```bash
kubectl get pv,pvc -n rabbitmq-system
```
Expected output:

```text
NAME                            CAPACITY   ACCESS MODES   RECLAIM POLICY   STATUS   STORAGECLASS    AGE
persistentvolume/nfs-video-pv   2T         RWX            Retain           Bound    nfs-nas-media   45s

NAME                                  STATUS   VOLUME         CAPACITY   ACCESS MODES   STORAGECLASS    AGE
persistentvolumeclaim/nfs-video-pvc   Bound    nfs-video-pv   2T         RWX            nfs-nas-media   42s
```
### Step 2: Debug Storage Mismatch Faults

If the status remains `Pending`, inspect the claim details for configuration mismatches:

```bash
kubectl describe pvc nfs-video-pvc -n rabbitmq-system
```
Common causes include:

- A mismatch between the `storageClassName` values in the PV and PVC.
- An NFS export that does not support the requested `ReadWriteMany` access mode.

## 3. Completed Pipeline Lifecycle Mapping
Once your storage layer is actively bound, the cluster components run in the following sequence:

1. **Ingest:** The ripping host writes the source file to `/mnt/nas/media/videos/raw_rips`.
2. **Queue:** The Python service publishes a task to RabbitMQ after the file closes.
3. **Scale:** KEDA adjusts the HandBrake deployment based on queue depth.
4. **Transcode:** Workers mount `nfs-video-pvc` at `/media/videos` and write outputs to the NAS.


