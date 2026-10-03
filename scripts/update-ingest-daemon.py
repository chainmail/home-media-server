#!/usr/bin/env python3
import time
import json
import os
import subprocess
import pika
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- INFRASTRUCTURE SETTINGS ---
RABBITMQ_HOST = "192.168.45.11"
RABBITMQ_PORT = 30072
QUEUE_NAME = "transcode_jobs"
WATCH_DIRECTORY = "/mnt/nas/media/raw_rips"

class VideoIngestHandler(FileSystemEventHandler):
    def get_video_resolution(self, file_path):
        """
        Uses ffprobe to extract the vertical height of the raw video file
        to determine if it is a DVD (480/576) or a Blu-ray (1080).
        """
        try:
            cmd = [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=height", "-of", "csv=p=0", file_path
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return int(result.stdout.strip())
        except Exception as e:
            print(f"[WARNING] Could not determine resolution via ffprobe: {e}. Defaulting to Blu-ray settings.")
            return 1080

    def on_closed(self, event):
        if event.is_directory:
            return

        file_path = event.src_path
        filename = os.path.basename(file_path)
        
        if not filename.lower().endswith(('.mkv', '.iso')):
            return

        print(f"[WATCHDOG] Completed file ingestion detected: {filename}")
        
        # Analyze file height to select correct cluster parameters
        height = self.get_video_resolution(file_path)
        if height <= 576:
            media_type = "dvd"
            print(f" -> Detected SD Resolution ({height}p). Assigning DVD profile (H.264).")
        else:
            media_type = "bluray"
            print(f" -> Detected HD Resolution ({height}p). Assigning Blu-ray profile (H.265 10-bit).")

        container_input = os.path.join("/media/videos/raw_rips", filename)
        container_output = os.path.join("/media/videos/transcoded_library", os.path.splitext(filename)[0] + ".mp4")

        payload = {
            "input_file": container_input,
            "output_name": container_output,
            "media_type": media_type # Injects media flag so the cluster worker applies the right flags
        }

        self.publish_to_queue(payload)

    def publish_to_queue(self, payload_data):
        try:
            credentials = pika.PlainCredentials('guest', 'guest')
            connection = pika.BlockingConnection(pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            ))
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE_NAME, durable=True)

            message_body = json.dumps(payload_data)
            channel.basic_publish(
                exchange='',
                routing_key=QUEUE_NAME,
                body=message_body,
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type='application/json'
                )
            )
            print(f"[RABBITMQ] Task metadata dispatched to cluster broker: {message_body}")
            connection.close()
        except Exception as e:
            print(f"[CONNECTION EXCEPTION] Pipeline failed to reach broker instance: {str(e)}")

if __name__ == "__main__":
    event_handler = VideoIngestHandler()
    observer = Observer()
    observer.schedule(event_handler, path=WATCH_DIRECTORY, recursive=False)
    print(f"[DAEMON STARTED] Monitoring ingest path: '{WATCH_DIRECTORY}'...")
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

