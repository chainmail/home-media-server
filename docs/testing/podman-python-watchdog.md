# Infrastructure Blueprint: Volume Isolation & Python Integration
**Local Test Network:** Podman-managed private subnet, separate from production.
**Host RabbitMQ Endpoint:** `127.0.0.1:5672` (published by Podman)
**Storage Architecture Target:** Local Host Bind Mounts (Simulating NFS Shares)  

---

## 1. Local Volume Mounting

Because rootless Podman operates entirely inside user space, mounting local directories into containers requires handling a security feature called **UID/GID mapping**. When you mount local host directories, Podman translates your local user permissions into the container's environment automatically.

### 1.1 Preparing the Mock Host Directories
On your Ripping/Ingest Host, create two directories to mimic your network storage shares:
```bash
mkdir -p /tmp/nas_mock/raw_rips /tmp/nas_mock/transcoded_library
```

### 1.2 Execution Command with Persistent Storage Mapping
To run your custom HandBrake container image locally while binding it to both your isolated network and your mock storage directories, use the following `podman run` command block. 

The `:z` flag is critical if you are running a Linux distribution with SELinux (like Fedora or RHEL), as it tells Podman to automatically relabel the shared storage volume paths to prevent permission denial bugs.

```bash
podman run -d \
  --name handbrake-worker-test \
  --network cluster-isolated-net \
    -e RABBITMQ_HOST=rabbitmq-test \
  -v /tmp/nas_mock/raw_rips:/media/videos/raw_rips:z \
  -v /tmp/nas_mock/transcoded_library:/media/videos/transcoded_library:z \
  localhost/handbrake-worker:latest
```

---

## 2. Automation Pipeline Daemon (`watchdog_test_producer.py`)

This Python daemon runs on the host and monitors `/tmp/nas_mock/raw_rips`. RabbitMQ is reached through the published local port at `127.0.0.1:5672`.

Save the code payload below exactly as `watchdog_test_producer.py`.

```python
#!/usr/bin/env python3
import time
import json
import os
import pika
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- INFRASTRUCTURE SETTINGS ---
# Connect through the published Podman port on the host
RABBITMQ_HOST = "127.0.0.1"
QUEUE_NAME = "transcode_jobs"

# Host path locations being actively watched
WATCH_DIRECTORY = "/tmp/nas_mock/raw_rips"

class VideoIngestHandler(FileSystemEventHandler):
    def on_closed(self, event):
        """
        Intercepts file events explicitly mapped to closure operations (IN_CLOSE_WRITE).
        Ensures the script triggers only when a video copy or rip operation finishes completely.
        """
        if event.is_directory:
            return

        file_path = event.src_path
        filename = os.path.basename(file_path)
        
        # Explicitly filter for raw media extensions
        if not filename.lower().endswith(('.mkv', '.iso')):
            return

        print(f"[WATCHDOG] Completed file ingestion detected: {filename}. Formatting cluster paths...")
        
        # Format the path mappings to match the interior target directories of your containers
        container_input = os.path.join("/media/videos/raw_rips", filename)
        container_output = os.path.join("/media/videos/transcoded_library", os.path.splitext(filename)[0] + ".mp4")

        payload = {
            "input_file": container_input,
            "output_name": container_output
        }

        self.publish_to_queue(payload)

    def publish_to_queue(self, payload_data):
        try:
            # Open persistent pipes connecting to the virtual containerized network interface
            credentials = pika.PlainCredentials('guest', 'guest')
            connection = pika.BlockingConnection(pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            ))
            channel = connection.channel()

            # Affirm queue settings match durable targets to maintain state logs
            channel.queue_declare(queue=QUEUE_NAME, durable=True)

            message_body = json.dumps(payload_data)
            
            # Route operational payload to the RabbitMQ queue
            channel.basic_publish(
                exchange='',
                routing_key=QUEUE_NAME,
                body=message_body,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Forces physical persistence on storage
                    content_type='application/json'
                )
            )
            print(f"[RABBITMQ] Task metadata successfully dispatched to queue broker: {message_body}")
            connection.close()

        except Exception as e:
            print(f"[CONNECTION EXCEPTION] Pipeline failed to reach broker instance: {str(e)}")

if __name__ == "__main__":
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

---

## 3. Run the Local Pipeline Test

1. Install the required Python dependencies on your ripping host:
   ```bash
   pip install pika watchdog
   ```
2. Start the testing network and the containerized RabbitMQ server using your `test_local_cluster.sh` script.
3. Start the python daemon in a dedicated terminal window:
   ```bash
   python3 watchdog_test_producer.py
   ```
4. Start your `handbrake-worker-test` container using the command block provided in **Section 1.2**.
5. Simulate a completed DVD rip by dropping a dummy video file into the watched folder:
   ```bash
   touch /tmp/nas_mock/raw_rips/movie_test.mkv
   ```

### Verification
* Check your Python terminal window. You should see a log confirmation stating that the `movie_test.mkv` payload metadata was generated and successfully pushed to RabbitMQ.
* Check your container runtime log outputs using `podman logs handbrake-worker-test`. You should see the container process pop the message from the queue and immediately engage its HandBrakeCLI execution threads against the file.

