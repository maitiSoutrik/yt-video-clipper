import os
import time
import logging
import subprocess
from youtube_transcript_api import YouTubeTranscriptApi
from typing import List, Dict, Any, Optional
import json
import requests
import sys
import re
from pydantic import BaseModel, Field


# load the environment variables
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('youtube_download.log')
    ]
)
logger = logging.getLogger(__name__)

# Get OpenRouter API key from environment variables
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3-opus")

if not OPENROUTER_API_KEY:
    print("Error: OPENROUTER_API_KEY environment variable is not set.")
    print("Please add your OpenRouter API key to the .env file.")
    sys.exit(1)

# Function to extract YouTube video ID from various URL formats
def extract_youtube_video_id(url):
    """Extract the video ID from various YouTube URL formats."""
    # Pattern for standard YouTube URLs (youtube.com/watch?v=VIDEO_ID)
    standard_pattern = r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})(?:&|\?|$)'
    
    # Pattern for YouTube shorts (youtube.com/shorts/VIDEO_ID)
    shorts_pattern = r'youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})(?:&|\?|$)'
    
    # Try standard pattern
    match = re.search(standard_pattern, url)
    if match:
        return match.group(1)
    
    # Try shorts pattern
    match = re.search(shorts_pattern, url)
    if match:
        return match.group(1)
    
    # If no patterns match but it looks like a valid video ID itself
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
        return url
    
    # No valid YouTube video ID found
    return None


# Function to download YouTube video with yt-dlp
def download_youtube_video(video_id: str, max_retries: int = 3) -> Optional[tuple]:
    """
    Download a YouTube video using yt-dlp.
    Returns a tuple of (video_title, filename) on success or None on failure.
    """
    clean_youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    logger.info(f"Attempting to download video with yt-dlp: {clean_youtube_url}")
    
    # Check if yt-dlp is available
    try:
        subprocess.run(["yt-dlp", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.error("yt-dlp is not installed")
        print("Error: yt-dlp is not installed. Please install it with: pip install yt-dlp")
        sys.exit(1)
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Download attempt {attempt}/{max_retries}")
            print(f"Downloading video (attempt {attempt}/{max_retries})...")
            
            # First, get video info to create a good filename
            cmd_info = [
                "yt-dlp",
                clean_youtube_url,
                "--print", "%(title)s",
                "--no-warnings",
                "--no-playlist"
            ]
            
            logger.info(f"Getting video info with command: {' '.join(cmd_info)}")
            result = subprocess.run(cmd_info, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                logger.error(f"Error getting video info: {result.stderr}")
                if attempt < max_retries:
                    time.sleep(2)
                    continue
                else:
                    print(f"Error getting video info: {result.stderr}")
                    return None
            
            # Get video title and create safe filename
            video_title = result.stdout.strip()
            logger.info(f"Video title: {video_title}")
            
            safe_title = video_title.replace(' ', '_').replace('/', '_').replace('\\', '_')
            safe_title = re.sub(r'[^\w\-_.]', '', safe_title)  # Remove any non-filename characters
            filename = f"downloaded_videos/video_{safe_title}.mp4"
            
            # Run yt-dlp to download the video
            cmd = [
                "yt-dlp",
                clean_youtube_url,
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "-o", filename,
                "--no-warnings",
                "--no-playlist"
            ]
            
            logger.info(f"Downloading video with command: {' '.join(cmd)}")
            print(f"Downloading: {video_title}")
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            if result.returncode != 0:
                logger.error(f"yt-dlp error: {result.stderr.decode()}")
                if attempt < max_retries:
                    logger.info(f"Retrying in 2 seconds...")
                    time.sleep(2)
                    continue
                else:
                    print(f"Error: Failed to download video: {result.stderr.decode()}")
                    return None
                
            print(f"Video downloaded successfully as {filename}")
            logger.info(f"Download completed: {filename}")
            
            return (video_title, filename)
            
        except Exception as e:
            logger.exception(f"Unexpected error on attempt {attempt}: {str(e)}")
            if attempt < max_retries:
                logger.info(f"Retrying in 2 seconds...")
                time.sleep(2)
            else:
                logger.error(f"Failed after {max_retries} attempts")
                print(f"\nError: Failed to download video after {max_retries} attempts:")
                print(f"  {str(e)}")
                return None
    
    return None


# Ask user for YouTube URL
youtube_url = input("Enter a YouTube URL: ")
logger.info(f"User provided URL: {youtube_url}")

# Extract video ID and validate
video_id = extract_youtube_video_id(youtube_url)
if not video_id:
    logger.error(f"Invalid YouTube URL provided: {youtube_url}")
    print("Error: Could not extract a valid YouTube video ID from the provided URL.")
    print("Please enter a valid YouTube URL in one of these formats:")
    print("- https://www.youtube.com/watch?v=VIDEO_ID")
    print("- https://youtu.be/VIDEO_ID")
    print("- https://www.youtube.com/shorts/VIDEO_ID")
    print("- VIDEO_ID (11 characters)")
    sys.exit(1)

logger.info(f"Extracted video ID: {video_id}")

os.makedirs("downloaded_videos", exist_ok=True)

# Download the video
download_result = download_youtube_video(video_id)

if not download_result:
    logger.error("Failed to download video")
    print("Error: Could not download the video. Please check your internet connection and try again with a different video.")
    sys.exit(1)
else:
    # Unpack the successful download result
    video_title, filename = download_result
    logger.info(f"Using downloaded video: {video_title} - {filename}")
    
    # Create safe title for output files
    safe_title = video_title.replace(' ', '_').replace('/', '_').replace('\\', '_')
    safe_title = re.sub(r'[^\w\-_.]', '', safe_title)

# Function to get available transcript languages
def get_available_transcript_languages(video_id):
    """Get a list of available languages for a video's transcripts."""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Get manually created transcripts
        manual_langs = []
        for transcript in transcript_list._manually_created_transcripts.values():
            manual_langs.append({
                'language_code': transcript.language_code,
                'language': transcript.language,
                'is_generated': False,
                'is_translatable': transcript.is_translatable
            })
            
        # Get auto-generated transcripts
        generated_langs = []
        for transcript in transcript_list._generated_transcripts.values():
            generated_langs.append({
                'language_code': transcript.language_code,
                'language': transcript.language, 
                'is_generated': True,
                'is_translatable': transcript.is_translatable
            })
            
        return {
            'manual': manual_langs,
            'generated': generated_langs
        }
    except Exception as e:
        logger.error(f"Error getting transcript languages: {str(e)}")
        return {'manual': [], 'generated': []}


# Function to get transcript with fallback to other languages and translation
def get_transcript_with_fallback(video_id):
    """
    Attempt to get a transcript with the following fallback strategy:
    1. Try English
    2. Try any manually created transcript and translate to English
    3. Try any auto-generated transcript and translate to English
    """
    logger.info(f"Fetching transcript for video ID: {video_id}")
    print("Fetching video transcript...")
    
    # Function to standardize transcript format (dict or object to dict)
    def standardize_transcript(transcript_data):
        """Convert transcript to standard dictionary format."""
        standardized = []
        for item in transcript_data:
            # Handle both dict-style and object-style access
            if hasattr(item, 'start') and hasattr(item, 'duration') and hasattr(item, 'text'):
                # Object with attributes
                entry = {
                    'start': item.start,
                    'duration': item.duration,
                    'text': item.text
                }
                standardized.append(entry)
            elif isinstance(item, dict) and 'start' in item and 'duration' in item and 'text' in item:
                # Already a dict
                standardized.append(item)
            else:
                # Unknown format, try best effort
                logger.warning(f"Unknown transcript format: {type(item)}")
                try:
                    # Try to convert to dict using __dict__ or vars()
                    entry = vars(item) if hasattr(item, '__dict__') else dict(item)
                    standardized.append(entry)
                except Exception as e:
                    logger.error(f"Could not convert transcript item: {e}")
        return standardized
    
    try:
        # First try English
        try:
            logger.info("Attempting to get English transcript directly")
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
            logger.info("Successfully fetched English transcript")
            return standardize_transcript(transcript), "English (direct)"
        except Exception as e:
            logger.info(f"English transcript not available: {str(e)}")
            
        # Get available languages
        available_langs = get_available_transcript_languages(video_id)
        logger.info(f"Available transcript languages: {available_langs}")
        print("English transcript not available, checking alternatives...")
        
        # Try manually created transcripts first (usually higher quality)
        if available_langs['manual']:
            for lang_info in available_langs['manual']:
                lang_code = lang_info['language_code']
                lang_name = lang_info['language']
                
                try:
                    logger.info(f"Trying manual transcript in {lang_name} ({lang_code})")
                    print(f"Trying manual transcript in {lang_name}...")
                    
                    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                    transcript_obj = transcript_list.find_transcript([lang_code])
                    
                    # If not English and translatable, translate to English
                    if lang_code != 'en' and lang_info['is_translatable']:
                        logger.info(f"Translating {lang_name} transcript to English")
                        print(f"Translating {lang_name} transcript to English...")
                        transcript_obj = transcript_obj.translate('en')
                        transcript = transcript_obj.fetch()
                        return standardize_transcript(transcript), f"{lang_name} (translated to English)"
                    else:
                        transcript = transcript_obj.fetch()
                        return standardize_transcript(transcript), lang_name
                except Exception as lang_e:
                    logger.info(f"Could not use {lang_name} transcript: {str(lang_e)}")
                    continue
        
        # Try auto-generated transcripts
        if available_langs['generated']:
            for lang_info in available_langs['generated']:
                lang_code = lang_info['language_code']
                lang_name = lang_info['language']
                
                try:
                    logger.info(f"Trying auto-generated transcript in {lang_name} ({lang_code})")
                    print(f"Trying auto-generated transcript in {lang_name}...")
                    
                    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                    transcript_obj = transcript_list.find_transcript([lang_code])
                    
                    # If not English and translatable, translate to English
                    if lang_code != 'en' and lang_info['is_translatable']:
                        logger.info(f"Translating {lang_name} transcript to English")
                        print(f"Translating {lang_name} transcript to English...")
                        transcript_obj = transcript_obj.translate('en')
                        transcript = transcript_obj.fetch()
                        return standardize_transcript(transcript), f"{lang_name} (auto-generated, translated to English)"
                    else:
                        transcript = transcript_obj.fetch()
                        return standardize_transcript(transcript), f"{lang_name} (auto-generated)"
                except Exception as lang_e:
                    logger.info(f"Could not use {lang_name} auto-generated transcript: {str(lang_e)}")
                    continue
                    
        # If we get here, no transcript could be fetched or translated
        raise Exception("No usable transcripts found in any language")
        
    except Exception as e:
        logger.exception(f"Error fetching transcript with fallbacks: {str(e)}")
        
        # Get detailed language availability for error message
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            available = "Available languages:\n"
            manual = list(transcript_list._manually_created_transcripts.values())
            generated = list(transcript_list._generated_transcripts.values())
            
            if manual:
                available += "Manual: " + ", ".join([f"{t.language} ({t.language_code})" for t in manual]) + "\n"
            if generated:
                available += "Auto-generated: " + ", ".join([f"{t.language} ({t.language_code})" for t in generated])
            
            error_msg = f"Could not fetch transcript: {str(e)}\n{available}"
        except:
            error_msg = f"Could not fetch transcript: {str(e)}"
            
        raise Exception(error_msg)


# Get the transcript with fallback to other languages
try:
    transcript, transcript_source = get_transcript_with_fallback(video_id)
    
    if not transcript:
        logger.warning("Transcript appears to be empty")
        print("Warning: Transcript appears to be empty.")
    else:
        logger.info(f"Transcript fetched successfully - {len(transcript)} segments from {transcript_source}")
        print(f"Transcript fetched successfully - {len(transcript)} segments from {transcript_source}")
        
        # Print a sample of the transcript
        if len(transcript) > 0:
            print("\nTranscript sample (first 3 segments):")
            for i, segment in enumerate(transcript[:min(3, len(transcript))]):
                # Use dict access - we've standardized the format
                start_time = segment.get('start', 0.0)
                text = segment.get('text', '[No text]')
                print(f"  {i+1}. [{start_time:.1f}s] {text}")
            if len(transcript) > 3:
                print("  ...")
except Exception as e:
    logger.exception(f"Error fetching transcript: {str(e)}")
    print(f"Error: {str(e)}")
    print("\nPlease try a different video with available transcripts.")
    sys.exit(1)

# Build prompt for OpenRouter API
# Convert transcript to simple text format for the prompt
def transcript_to_text(transcript_data):
    """Convert transcript data to simple text format for the prompt."""
    text_parts = []
    for segment in transcript_data:
        start_time = segment.get('start', 0)
        text = segment.get('text', '')
        text_parts.append(f"[{start_time:.2f}s] {text}")
    return "\n".join(text_parts)

# Format transcript as text
transcript_text = transcript_to_text(transcript)

prompt = f"""Provided to you is a transcript of a video. 
Please identify all segments that can be extracted as viral short-form content 
from the video based on the transcript.

IMPORTANT REQUIREMENTS:
1. Each segment MUST be between 15-60 seconds in duration (ideal for platforms like TikTok, YouTube Shorts, and Instagram Reels)
2. Each segment MUST have a clear hook and standalone value that works without context
3. Focus on segments with surprising facts, controversial statements, emotional moments, or valuable insights
4. Make sure you provide extremely accurate timestamps
5. For each segment, recommend the best platform(s) from: YouTube Shorts, TikTok, Instagram Reels, LinkedIn

YOUR RESPONSE MUST BE IN JSON FORMAT with the following structure:
{{
  "segments": [
    {{
      "start_time": <start time in seconds>,
      "end_time": <end time in seconds>,
      "yt_title": "<catchy, attention-grabbing title for the segment>",
      "description": "<detailed description highlighting viral potential>",
      "duration": <duration in seconds>,
      "hook": "<opening line or concept that grabs attention>",
      "platforms": ["platform1", "platform2", ...],
      "hashtags": ["#hashtag1", "#hashtag2", ...]
    }},
    ... more segments ...
  ]
}}

Here is the transcription: 
{transcript_text}"""

messages = [
    {"role": "system", "content": "You are a viral short-form content expert specialized in identifying segments that can go viral on platforms like TikTok, YouTube Shorts, and Instagram Reels. You understand what makes content shareable and engaging in 15-60 second formats. You MUST respond in valid JSON format with properly structured data."},
    {"role": "user", "content": prompt}
]

# Function to parse text response into structured JSON
def parse_text_response(text: str) -> Dict[str, Any]:
    """
    Parse a text response from OpenRouter into a structured JSON format.
    Expected format in text:
    Subtopic X:
    Title: <title>
    Start: <start_time>
    End: <end_time>
    Duration: <duration> seconds
    """
    logger.info("Parsing text response into structured format")
    
    # Extract segments using regex pattern
    segments = []
    
    # Different regex patterns to try
    patterns = [
        # Pattern 1: Standard format with "Title:", "Start:", "End:", "Duration:"
        r'(?:Subtopic\s+\d+:?\s*\n?)?'
        r'(?:Title:?\s*)(.*?)\s*\n'
        r'(?:Start:?\s*)(\d+(?:\.\d+)?)\s*\n'
        r'(?:End:?\s*)(\d+(?:\.\d+)?)\s*\n'
        r'(?:Duration:?\s*)(\d+(?:\.\d+)?)',
        
        # Pattern 2: Format with time information in different format
        r'(?:Subtopic\s+\d+:?\s*)(.*?)\s*\n'
        r'(?:Start:?\s*|Start\sTime:?\s*)(\d+(?:\.\d+)?)\s*\n'
        r'(?:End:?\s*|End\sTime:?\s*)(\d+(?:\.\d+)?)\s*\n'
        r'(?:Duration:?\s*)(\d+(?:\.\d+)?)',
    ]
    
    # Try each pattern
    matches = []
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.DOTALL | re.MULTILINE)
        segments_found = list(matches)
        if segments_found:
            print(f"Found {len(segments_found)} segments using pattern")
            break
    
    # If no matches found with regex, try a line-by-line parsing approach
    if not segments_found:
        print("No segments found with regex patterns, attempting alternative parsing")
        segments_found = parse_segments_manually(text)
    
    # Process found segments
    for i, match in enumerate(segments_found):
        if isinstance(match, tuple):  # For manual parsing results
            title, start_time, end_time, duration = match
        else:  # For regex results
            if len(match.groups()) >= 4:
                title = match.group(1).strip()
                start_time = float(match.group(2))
                end_time = float(match.group(3))
                duration = float(match.group(4))
            else:
                print(f"Warning: Skipping segment with insufficient data: {match.groups()}")
                continue
                
        segment = {
            "start_time": start_time,
            "end_time": end_time,
            "yt_title": title,
            "description": f"Extracted segment {i+1} from the video featuring: {title}",
            "duration": int(duration)
        }
        segments.append(segment)
    
    if not segments:
        print("Warning: No segments could be parsed from the response")
        print("Raw text:", text[:200] + "..." if len(text) > 200 else text)
        # Create a default segment
        segments.append({
            "start_time": 0,
            "end_time": 60,
            "yt_title": "Default segment - Parser could not extract segments",
            "description": "This is a default segment created because the parser could not extract segments from the API response.",
            "duration": 60
        })
    
    return {"segments": segments}


def parse_segments_manually(text: str) -> List[tuple]:
    """
    Manual line-by-line parsing for cases where regex fails
    Returns a list of tuples (title, start_time, end_time, duration)
    """
    lines = text.split('\n')
    segments = []
    current_title = None
    current_start = None
    current_end = None
    current_duration = None
    
    for line in lines:
        line = line.strip()
        
        # Skip empty lines
        if not line:
            continue
            
        # Check if this is a new segment indicator
        if re.match(r'^(?:Subtopic|Segment)\s+\d+', line):
            # Save previous segment if we have one
            if all([current_title, current_start is not None, current_end is not None]):
                if current_duration is None:
                    current_duration = current_end - current_start
                segments.append((current_title, current_start, current_end, current_duration))
            
            # Extract title if it's on the same line as "Subtopic X:"
            title_match = re.search(r'^(?:Subtopic|Segment)\s+\d+:?\s*(.*?)$', line)
            if title_match and title_match.group(1):
                current_title = title_match.group(1).strip()
            else:
                current_title = None
            current_start = None
            current_end = None
            current_duration = None
            
        # Look for title
        elif re.search(r'^(?:Title|Topic):\s', line, re.IGNORECASE):
            current_title = re.sub(r'^(?:Title|Topic):\s+', '', line, flags=re.IGNORECASE).strip()
            
        # Look for start time
        elif re.search(r'^Start(?:\s+Time)?:\s', line, re.IGNORECASE):
            time_str = re.sub(r'^Start(?:\s+Time)?:\s+', '', line, flags=re.IGNORECASE).strip()
            try:
                # Try to handle different time formats (seconds, mm:ss, etc.)
                if ':' in time_str:
                    parts = time_str.split(':')
                    if len(parts) == 2:
                        current_start = float(parts[0]) * 60 + float(parts[1])
                    elif len(parts) == 3:
                        current_start = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                else:
                    current_start = float(time_str.split()[0])
            except (ValueError, IndexError):
                print(f"Warning: Could not parse start time from '{time_str}'")
                
        # Look for end time
        elif re.search(r'^End(?:\s+Time)?:\s', line, re.IGNORECASE):
            time_str = re.sub(r'^End(?:\s+Time)?:\s+', '', line, flags=re.IGNORECASE).strip()
            try:
                # Try to handle different time formats
                if ':' in time_str:
                    parts = time_str.split(':')
                    if len(parts) == 2:
                        current_end = float(parts[0]) * 60 + float(parts[1])
                    elif len(parts) == 3:
                        current_end = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                else:
                    current_end = float(time_str.split()[0])
            except (ValueError, IndexError):
                print(f"Warning: Could not parse end time from '{time_str}'")
                
        # Look for duration
        elif re.search(r'^Duration:\s', line, re.IGNORECASE):
            duration_str = re.sub(r'^Duration:\s+', '', line, flags=re.IGNORECASE).strip()
            try:
                # Remove "seconds" or "s" if present
                duration_str = re.sub(r'\s*(?:seconds|s)$', '', duration_str, flags=re.IGNORECASE)
                current_duration = float(duration_str.split()[0])
            except (ValueError, IndexError):
                print(f"Warning: Could not parse duration from '{duration_str}'")
    
    # Add the last segment if we have one
    if all([current_title, current_start is not None, current_end is not None]):
        if current_duration is None:
            current_duration = current_end - current_start
        segments.append((current_title, current_start, current_end, current_duration))
    
    return segments


# Function to call OpenRouter API
def call_openrouter_api(messages: List[Dict[str, str]], model: str = OPENROUTER_MODEL) -> Dict[str, Any]:
    """Call the OpenRouter API with the given messages."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # For GPT models we conditionally use response_format
    if "gpt" in model.lower():
        logger.info(f"Using JSON response format for GPT model")
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "response_format": {"type": "json_object"}
        }
    else:
        logger.info(f"Using standard response format for non-GPT model")
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7
        }
    
    try:
        print(f"Calling OpenRouter API with model {model}...")
        response = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload
        )
        
        # Check if we got an API error response
        if response.status_code != 200:
            logger.error(f"API Error: {response.status_code} - {response.text}")
            print(f"Error from OpenRouter API: Status {response.status_code}")
            print(f"Details: {response.text}")
            
            # Try a fallback approach if it's a formatting error
            if response.status_code == 400 and "gpt" in model.lower() and "response_format" in response.text:
                logger.info("Trying fallback without response_format")
                print("Trying again without JSON format requirement...")
                payload.pop("response_format", None)
                
                response = requests.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload
                )
                if response.status_code != 200:
                    logger.error(f"Fallback API Error: {response.status_code} - {response.text}")
                    print(f"Fallback attempt also failed with status {response.status_code}")
                    sys.exit(1)
            else:
                sys.exit(1)
        
        response_data = response.json()
        
        # Check if we got a proper API response with choices
        if not response_data or "choices" not in response_data or not response_data["choices"]:
            logger.error(f"Invalid API response structure: {response_data}")
            print("Error: OpenRouter API returned an invalid response structure")
            print(f"Response: {response_data}")
            sys.exit(1)
        
        # Get the content from the response
        content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        
        # Try to parse as JSON
        try:
            # Clean up the content in case it has markdown code blocks
            clean_content = content
            
            # Handle content wrapped in markdown code blocks
            json_block_match = re.search(r'```(?:json)?\s*({[\s\S]*?})\s*```', content)
            if json_block_match:
                clean_content = json_block_match.group(1)
                logger.info("Extracted JSON from code block")
            
            content_json = json.loads(clean_content)
            logger.info("Successfully parsed JSON response")
            
            # Modify the response to contain the cleaned JSON
            modified_response = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(content_json)
                        }
                    }
                ]
            }
            return modified_response
            
        except json.JSONDecodeError:
            # If not valid JSON, try to parse the text response
            logger.info("Response is not valid JSON, attempting to parse text response")
            print("Response is not in JSON format. Attempting to parse as text...")
            structured_data = parse_text_response(content)
            
            # Create a modified response with the parsed data
            modified_response = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(structured_data)
                        }
                    }
                ]
            }
            return modified_response
            
    except requests.exceptions.RequestException as e:
        logger.exception(f"Error calling OpenRouter API: {str(e)}")
        print(f"Error calling OpenRouter API: {str(e)}")
        if response := getattr(e, "response", None):
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.text}")
        sys.exit(1)

class Segment(BaseModel):
    """ Represents a segment of a video optimized for short-form content"""
    start_time: float = Field(..., description="The start time of the segment in seconds")
    end_time: float = Field(..., description="The end time of the segment in seconds")
    yt_title: str = Field(..., description="The catchy, attention-grabbing title for the segment")
    description: str = Field(..., description="The detailed description highlighting viral potential")
    duration: int = Field(..., description="The duration of the segment in seconds")
    hook: str = Field(default="", description="Opening line or concept that grabs attention")
    platforms: List[str] = Field(default_factory=list, description="List of recommended platforms (YouTube Shorts, TikTok, Instagram Reels, LinkedIn)")
    hashtags: List[str] = Field(default_factory=list, description="List of relevant hashtags for the content")

class VideoTranscript(BaseModel):
    """ Represents the transcript of a video with identified viral short-form segments"""
    segments: List[Segment] = Field(..., description="List of viral short-form segments in the video")

# Call OpenRouter API
print("Analyzing video transcript with AI to identify viral segments...")
try:
    api_response = call_openrouter_api(messages)
    
    # Validate API response structure
    if not api_response or "choices" not in api_response or not api_response["choices"]:
        print("Error: Invalid response format from OpenRouter API")
        print("Raw response:", api_response)
        sys.exit(1)
    
    # Extract content from response
    content = api_response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    
    # Parse the JSON response
    try:
        content_json = json.loads(content)
        
        # Verify segments key exists
        if "segments" not in content_json:
            print("Error: Response missing 'segments' key in JSON object")
            print("Raw response:", content)
            sys.exit(1)
            
        # Validate using our Pydantic model
        video_transcript = VideoTranscript.parse_obj(content_json)
        parsed_content = video_transcript.dict()['segments']
        print(f"Found {len(parsed_content)} potential viral segments")
    except json.JSONDecodeError:
        print("Error: Invalid JSON response from OpenRouter API")
        print("Raw response:", content)
        sys.exit(1)
    except Exception as e:
        print(f"Error parsing response: {str(e)}")
        print("Raw response:", content)
        sys.exit(1)
except Exception as e:
    print(f"Error analyzing transcript: {str(e)}")
    sys.exit(1)
# Create a folder to store clips
os.makedirs("generated_clips", exist_ok=True)

# Create platform-specific folders for easier organization
platforms = ["YouTube_Shorts", "TikTok", "Instagram_Reels", "LinkedIn"]
for platform in platforms:
    os.makedirs(f"generated_clips/{platform}", exist_ok=True)

segment_labels = []

print("Generating short-form video clips for each segment...")
for i, segment in enumerate(parsed_content):
    start_time = segment['start_time']
    end_time = segment['end_time']
    yt_title = segment['yt_title']
    description = segment['description']
    duration = segment['duration']
    
    print(f"Processing segment {i+1}: {yt_title} ({duration}s)")
    
    # Create base output file
    output_file = f"generated_clips/{safe_title}_{str(i+1)}.mp4"
    
    # Get platforms for this clip (default to all if none specified)
    clip_platforms = segment.get('platforms', platforms)
    
    try:
        # Extract clip with higher quality for short-form content
        command = f"ffmpeg -i {filename} -ss {start_time} -to {end_time} -c:v libx264 -preset slow -crf 18 -c:a aac -b:a 192k {output_file}"
        result = subprocess.call(command, shell=True)
        
        if result != 0:
            print(f"Warning: FFmpeg exited with code {result} for segment {i+1}")
        else:
            print(f"Clip generated: {output_file}")
            
            # Create platform-specific versions
            for platform in clip_platforms:
                platform_dir = f"generated_clips/{platform}"
                platform_file = f"{platform_dir}/{safe_title}_{str(i+1)}.mp4"
                
                # Create platform-specific version if it doesn't exist
                if not os.path.exists(platform_file):
                    try:
                        os.symlink(os.path.relpath(output_file, platform_dir), platform_file)
                        print(f"Linked to {platform}")
                    except Exception as link_error:
                        print(f"Warning: Could not link to {platform}: {str(link_error)}")
            
        # Get additional fields with defaults if they don't exist
        hook = segment.get('hook', '')
        platforms = segment.get('platforms', [])
        hashtags = segment.get('hashtags', [])
        
        # Create formatted platform and hashtag strings
        platforms_str = ", ".join(platforms) if platforms else "All platforms"
        hashtags_str = " ".join(hashtags) if hashtags else ""
        
        segment_labels.append(f"Clip {i+1}: {yt_title}, Duration: {duration}s\n" +
                             f"Hook: {hook}\n" +
                             f"Description: {description}\n" +
                             f"Recommended platforms: {platforms_str}\n" +
                             f"Hashtags: {hashtags_str}\n")
    except Exception as e:
        print(f"Error generating clip for segment {i+1}: {str(e)}")

# Save the segment labels to a text file
print("Saving segment metadata...")
with open('generated_clips/segment_labels.txt', 'w') as f:
    for label in segment_labels:
        f.write(label + "\n")

# Save the segments to a JSON file
with open('generated_clips/segments.json', 'w') as f:
    json.dump(parsed_content, f, indent=4)

# Count clips in each platform folder
platform_counts = {}
for platform in platforms:
    platform_dir = f"generated_clips/{platform}"
    if os.path.exists(platform_dir):
        platform_counts[platform] = len([f for f in os.listdir(platform_dir) if f.endswith('.mp4')])

platform_summary = ", ".join([f"{platform}: {count}" for platform, count in platform_counts.items()])

print(f"Process complete! {len(parsed_content)} short-form clips generated in the 'generated_clips' folder.")
print(f"Platform distribution: {platform_summary}")
print("You can find platform-specific clips in the respective platform folders.")
