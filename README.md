# YouTube Viral Clip Finder

This tool automatically downloads a YouTube video, analyzes its transcript using AI to identify potentially viral short-form segments, and generates video clips for platforms like TikTok, YouTube Shorts, and Instagram Reels.

## Features

* Downloads YouTube videos (including Shorts).
* Retrieves video transcripts, handling multiple languages and translations.
* Uses AI (via OpenRouter API) to find engaging segments suitable for short-form content.
* Extracts video clips based on AI analysis using FFmpeg.
* Organizes generated clips into platform-specific folders.
* Outputs metadata (titles, descriptions, hashtags, etc.) for each clip.

## Requirements

* Python 3.7+
* External Tools:
  * `ffmpeg`: For video processing. [Install Instructions](https://ffmpeg.org/download.html)
  * `yt-dlp`: For downloading YouTube videos. Install via pip (`pip install yt-dlp`) or see [yt-dlp GitHub](https://github.com/yt-dlp/yt-dlp#installation).
* Python packages (see `requirements.txt`):
  * `pytube`
  * `python-dotenv`
  * `youtube_transcript_api`
* API Keys:
  * OpenRouter API Key: Get one from [OpenRouter.ai](https://openrouter.ai/)

## Setup

1. **Clone the repository (optional):**

   ```bash
   # If you have git installed
   # git clone <repository_url>
   # cd <repository_directory>
   ```

   Or simply download the files.

2. **Create a virtual environment:**

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install Python dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Install `yt-dlp` (if not already installed globally):**

   ```bash
   pip install yt-dlp
   ```

5. **Install `ffmpeg`:**
   * **macOS (using Homebrew):** `brew install ffmpeg`
   * **Linux (Debian/Ubuntu):** `sudo apt update && sudo apt install ffmpeg`
   * **Windows:** Download from the [official FFmpeg website](https://ffmpeg.org/download.html) and add it to your system's PATH.

6. **Configure API Key:**
   * Create a file named `.env` in the project's root directory.
   * Add your OpenRouter API key to the `.env` file:

     ```dotenv
     OPENROUTER_API_KEY='your_openrouter_api_key_here'
     # Optional: Specify a different model or base URL
     # OPENROUTER_MODEL='anthropic/claude-3-haiku'
     # OPENROUTER_BASE_URL='https://api.example.com/v1'
     ```

## Usage

1. Make sure your virtual environment is activated.
2. Run the main script:

   ```bash
   python main.py
   ```

3. The script will prompt you to enter a YouTube URL.
4. It will then perform the download, analysis, and clip generation steps, printing progress to the console and logging details to `youtube_download.log`.

## Output

The script generates the following outputs in the project directory:

* `downloaded_videos/`: Contains the full downloaded YouTube video.
* `generated_clips/`: Contains the extracted short-form video clips.
  * `*.mp4`: Base video clips.
  * `YouTube_Shorts/`, `TikTok/`, `Instagram_Reels/`, `LinkedIn/`: Subfolders containing links to the relevant clips for each platform.
* `generated_clips/segment_labels.txt`: A text file with details (title, hook, description, platforms, hashtags) for each generated clip.
* `generated_clips/segments.json`: A JSON file containing the structured data for all generated segments.
* `youtube_download.log`: Log file with details about the script's execution.

## How It Works

1. **Video Download:** Uses `yt-dlp` to download the video specified by the input URL.
2. **Transcript Fetching:** Uses `youtube_transcript_api` to get the video transcript. It prioritizes English but can fetch transcripts in other languages and translate them if necessary.
3. **AI Analysis:** Sends the transcript text to the OpenRouter API (using the model specified in `.env` or defaulting to `anthropic/claude-3-opus`) with a prompt asking it to identify viral segments and return structured JSON data (start/end times, title, description, hook, platforms, hashtags).
4. **Clip Generation:** Uses `ffmpeg` to precisely cut the video segments based on the start and end times identified by the AI.
5. **Organization:** Creates directories for common platforms and links the generated clips into the appropriate folders.
