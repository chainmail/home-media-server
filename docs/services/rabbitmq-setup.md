# Manifest 2: Containerized RabbitMQ & Management Service Manifests
**Target Namespace:** `rabbitmq-system`  
**Storage Engine:** Local NVMe Mount  
**Network Service Type:** NodePort / Ingress  

---

## 1. Kubernetes RabbitMQ Manifest

This production manifest deploys a fully containerized **RabbitMQ Server instance** directly into the Talos cluster environment. The deployment explicitly enables the **Management Plugin UI** and exposes it across the `192.168.45.0/24` cluster boundary using a `NodePort` mapping.

Save this document as `rabbitmq-cluster.yaml` and deploy it by running:  
`kubectl apply -f rabbitmq-cluster.yaml`

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
          - k8s-worker-01 # Binds to the specific worker node tracking this NVMe share
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
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rabbitmq-server
  namespace: rabbitmq-system
  labels:
    app: rabbitmq
spec:
  replicas: 1
  selector:
    matchLabels:
      app: rabbitmq
  template:
    metadata:
      labels:
        app: rabbitmq
    spec:
      containers:
      - name: rabbitmq
        image: rabbitmq:3.13-management-alpine # Container image with UI management pre-compiled
        ports:
        - name: amqp
          containerPort: 5672 # Main application messaging port
        - name: http-mgmt
          containerPort: 15672 # Management Web UI Interface Port
        env:
        - name: RABBITMQ_DEFAULT_USER
          value: "cluster_admin"
        - name: RABBITMQ_DEFAULT_PASS
          value: "SecureTranscodePass2026"
        volumeMounts:
        - name: rabbitmq-data
          mountPath: /var/lib/rabbitmq
      volumes:
      - name: rabbitmq-data
        persistentVolumeClaim:
          claimName: rabbitmq-nvme-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: rabbitmq-nodeport-service
  namespace: rabbitmq-system
spec:
  type: NodePort
  selector:
    app: rabbitmq
  ports:
    - name: amqp
      port: 5672
      targetPort: 5672
      nodePort: 30072 # Internal cluster communication pipe
    - name: management
      port: 15672
      targetPort: 15672
      nodePort: 31672 # Exposes the Management UI dashboard across the network framework
```

### 1.2 Accessing the RabbitMQ Management Interface
Because the service is exposed as a cluster `NodePort`, the management dashboard is now reachable from outside the isolated network layer. 

1. From any management workstation on your primary network (`192.168.1.0/24`), open a web browser.
2. Navigate to the IP address of any one of your active Talos nodes on the cluster network using the exposed NodePort:  
   `http://192.168.45.11:31672`
3. The AMQP endpoint for a host-side producer is `192.168.45.11:30072`; the home router route carries traffic from `192.168.1.0/24` to the cluster subnet.
4. Authenticate using the configured environment credentials:
   *   **Username:** `cluster_admin`
   *   **Password:** `SecureTranscodePass2026`

