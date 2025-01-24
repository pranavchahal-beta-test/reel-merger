import os
import uuid
import subprocess
import json
from flask import Flask, request, render_template, send_from_directory

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
COMBINED_FOLDER = 'combined'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(COMBINED_FOLDER, exist_ok=True)


@app.route('/', methods=['GET'])
def index():
    """
    Renders an HTML form to upload the "top" MP4, "bottom" MP4,
    and choose which audio to keep.
    """
    return render_template('index.html')


@app.route('/merge', methods=['POST'])
def merge_videos():
    """
    Receives the files and audio choice, then processes via FFmpeg.
    Provides a download link for the merged result.
    """
    top_file = request.files['top_video']
    bottom_file = request.files['bottom_video']
    audio_source = request.form.get('audio_source')

    if not top_file or not bottom_file:
        return "Error: Please upload both top and bottom MP4 files."


    top_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}_top.mp4")
    bottom_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}_bottom.mp4")
    top_file.save(top_path)
    bottom_file.save(bottom_path)


    output_filename = f"{uuid.uuid4()}_merged.mp4"
    output_path = os.path.join(COMBINED_FOLDER, output_filename)


    try:
        stack_videos_9x16(top_path, bottom_path, output_path, audio_source)
    except subprocess.CalledProcessError as e:

        return f"""
        <h1>FFmpeg Error</h1>
        <p>The FFmpeg command failed with error code {e.returncode}.</p>
        <pre>{e}</pre>
        """

    return f"""
    <h1>Video Merged Successfully!</h1>
    <p><a href="/download/{output_filename}">Download merged video</a></p>
    <p><a href="/">Go back</a></p>
    """


@app.route('/download/<filename>')
def download_file(filename):
    """Serve the merged file for download."""
    return send_from_directory(COMBINED_FOLDER, filename, as_attachment=True)


def get_video_duration(path):
    """
    Use ffprobe to get the video's duration (in seconds) as a float.
    Requires ffmpeg/ffprobe to be installed and on PATH.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-of", "json",
        path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    data = json.loads(result.stdout)
    return float(data['format']['duration'])


def stack_videos_9x16(top_path, bottom_path, output_path, audio_source):
    """
    Vertically stack two MP4 videos in a final resolution of 1080x1920 (9:16).
    Each video is scaled to 1080x960 before stacking.

    - If audio_source='top': keep top's audio, loop bottom if top is longer; final length = top's duration.
    - If audio_source='bottom': keep bottom's audio, loop top if bottom is longer; final length = bottom's duration.
    - If audio_source='none': no audio, no looping, final ends at the shorter track via -shortest.
    """



    scale_filter_top = "scale=1080:960"
    scale_filter_bottom = "scale=1080:960"

    if audio_source == 'top':
        top_duration = get_video_duration(top_path)
        command = [
            "ffmpeg",
            "-y",
            "-i", top_path,
            "-stream_loop", "-1", "-i", bottom_path,
            "-filter_complex",
            f"[0:v]{scale_filter_top}[v0];[1:v]{scale_filter_bottom}[v1];[v0][v1]vstack=inputs=2[v]",
            "-map", "[v]",
            "-map", "0:a",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-strict", "experimental",
            "-t", str(top_duration),
            output_path
        ]
        subprocess.run(command, check=True)

    elif audio_source == 'bottom':
        bottom_duration = get_video_duration(bottom_path)
        command = [
            "ffmpeg",
            "-y",
            "-stream_loop", "-1", "-i", top_path,
            "-i", bottom_path,
            "-filter_complex",
            f"[0:v]{scale_filter_top}[v0];[1:v]{scale_filter_bottom}[v1];[v0][v1]vstack=inputs=2[v]",
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-strict", "experimental",
            "-t", str(bottom_duration),
            output_path
        ]
        subprocess.run(command, check=True)

    else:

        command = [
            "ffmpeg",
            "-y",
            "-i", top_path,
            "-i", bottom_path,
            "-filter_complex",
            f"[0:v]{scale_filter_top}[v0];[1:v]{scale_filter_bottom}[v1];[v0][v1]vstack=inputs=2[v]",
            "-map", "[v]",
            "-an",
            "-c:v", "libx264",
            "-strict", "experimental",
            "-shortest",
            output_path
        ]
        subprocess.run(command, check=True)


if __name__ == "__main__":
    app.run(debug=True)
