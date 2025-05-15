import os
import json
import requests
import logging
import sys
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ValidationError

import config

logger = logging.getLogger(__name__)

# Pydantic Models for AI Response structure
class Segment(BaseModel):
    """Represents a segment of a video optimized for short-form content"""
    start_time: float = Field(..., description="The start time of the segment in seconds")
    end_time: float = Field(..., description="The end time of the segment in seconds")
    duration: float = Field(..., description="The duration of the segment in seconds")
    yt_title: str = Field(..., description="A catchy YouTube title for this segment (max 70 chars)")
    hook: str = Field(..., description="A hook for the video (first 3-5 seconds)")
    description: str = Field(..., description="A brief description of the segment's content")
    platforms: List[str] = Field(default_factory=lambda: ["TikTok", "YouTube_Shorts", "Instagram_Reels"], description="List of platforms this segment is suitable for")
    hashtags: List[str] = Field(default_factory=list, description="List of relevant hashtags for the content")

class VideoTranscript(BaseModel):
    """Represents the transcript of a video with identified viral short-form segments"""
    segments: List[Segment] = Field(..., description="List of viral short-form segments in the video")

def build_ai_prompt(transcript_text: str) -> List[Dict[str, str]]:
    """Constructs the messages array for the OpenRouter API call."""
    prompt_template = f"""Provided to you is a transcript of a video. 
Your task is to identify all segments that can be extracted as engaging, viral short-form content (15-60 seconds) suitable for platforms like TikTok, YouTube Shorts, and Instagram Reels.
For each segment, provide:
1.  `start_time`: The precise start time of the segment in seconds (float).
2.  `end_time`: The precise end time of the segment in seconds (float).
3.  `duration`: The duration of the segment in seconds (float, calculated as end_time - start_time).
4.  `yt_title`: A catchy, concise YouTube title for this segment (max 70 characters).
5.  `hook`: A compelling hook for the video, describing the first 3-5 seconds to grab attention.
6.  `description`: A brief summary of the segment's content and why it's engaging.
7.  `platforms`: A list of specific platforms (e.g., ["TikTok", "YouTube_Shorts"]) for which this segment is best suited. Default to ["TikTok", "YouTube_Shorts", "Instagram_Reels"] if unsure.
8.  `hashtags`: A list of relevant hashtags (e.g., ["#viral", "#funnyclips"]).

Respond ONLY with a valid JSON object containing a single key "segments", which is a list of these segment objects. Ensure all times are in seconds. Validate durations. Make sure the JSON is well-formed.

Example of a segment object:
{{
  "start_time": 120.5,
  "end_time": 150.0,
  "duration": 29.5,
  "yt_title": "Amazing Trick Shot!",
  "hook": "You won't believe what happens next!",
  "description": "A skilled performer lands an incredible trick shot that defies expectations.",
  "platforms": ["TikTok", "Instagram_Reels"],
  "hashtags": ["#trickshot", "#amazing", "#skill"]
}}

Here is the transcription: 
{transcript_text}"""

    messages = [
        {"role": "system", "content": "You are a viral short-form content expert. You identify segments from video transcripts that can go viral on platforms like TikTok, YouTube Shorts, and Instagram Reels. You MUST respond ONLY with a valid JSON object as specified. The JSON should have a single top-level key 'segments' which is a list of segment objects. Do not add any explanatory text before or after the JSON object."},
        {"role": "user", "content": prompt_template}
    ]
    return messages

def _parse_segments_manually(text: str) -> List[Dict[str, Any]]:
    """Manual line-by-line parsing for cases where regex/JSON fails."""
    segments = []
    current_segment = {}
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line: continue

        # Simple heuristic: if a line looks like a new segment identifier or a clear field
        if line.lower().startswith("subtopic") or line.lower().startswith("segment"):
            if current_segment: # Save previous segment if populated
                segments.append(current_segment)
            current_segment = {}
            # Try to extract title from this line itself if possible
            if ':' in line:
                try: current_segment['yt_title'] = line.split(':', 1)[1].strip()
                except: pass # Ignore if split fails
            continue

        try:
            key, value = line.split(':', 1)
            key = key.strip().lower().replace(' ', '_')
            value = value.strip()

            if key == 'title' or key == 'yt_title': current_segment['yt_title'] = value
            elif key == 'start' or key == 'start_time': current_segment['start_time'] = float(re.findall(r"[\d\.]+", value)[0])
            elif key == 'end' or key == 'end_time': current_segment['end_time'] = float(re.findall(r"[\d\.]+", value)[0])
            elif key == 'duration': 
                match = re.search(r"([\d\.]+)\s*s", value, re.IGNORECASE)
                if match: current_segment['duration'] = float(match.group(1))
            elif key == 'hook': current_segment['hook'] = value
            elif key == 'description': current_segment['description'] = value
            elif key == 'platforms': current_segment['platforms'] = [p.strip() for p in value.split(',')]
            elif key == 'hashtags': current_segment['hashtags'] = [h.strip() for h in value.replace('#', '').split(',') if h.strip()]
        except ValueError as e:
            logger.debug(f"Manual parsing: Could not parse line '{line}': {e}")
        except Exception as e:
            logger.debug(f"Manual parsing: Generic error on line '{line}': {e}")

    if current_segment: # Add the last segment
        segments.append(current_segment)
    
    # Post-process to ensure required fields and calculate duration if missing
    processed_segments = []
    for seg_idx, seg in enumerate(segments):
        if 'start_time' in seg and 'end_time' in seg and 'duration' not in seg:
            seg['duration'] = round(seg['end_time'] - seg['start_time'], 2)
        if not all(k in seg for k in ['yt_title', 'start_time', 'end_time', 'duration', 'hook', 'description']):
            logger.warning(f"Manual parsing: Segment {seg_idx+1} is missing required fields: {seg}. Skipping.")
            continue
        # Default platforms and hashtags if missing
        if 'platforms' not in seg: seg['platforms'] = ["TikTok", "YouTube_Shorts", "Instagram_Reels"]
        if 'hashtags' not in seg: seg['hashtags'] = []
        processed_segments.append(seg)

    logger.info(f"Manually parsed {len(processed_segments)} segments.")
    return processed_segments

def parse_ai_text_response(text: str) -> Optional[Dict[str, Any]]:
    """Fallback parser for when AI response is not valid JSON. Uses regex and manual parsing."""
    logger.warning("AI response was not valid JSON. Attempting fallback text parsing.")
    segments = []
    
    # Attempt 1: Regex for common structured text (example from original main.py)
    # This regex is quite specific and might need adjustment based on actual non-JSON outputs.
    pattern = re.compile(
        r"Subtopic \d+: (.*?)\n" +
        r"Title: (.*?)\n" +
        r"Start: (\d+\.\d+|\d+:\d+:\d+\.\d+|\d+:\d+:\d+|\d+:\d+s|\d+s)s?\n" +
        r"End: (\d+\.\d+|\d+:\d+:\d+\.\d+|\d+:\d+:\d+|\d+:\d+s|\d+s)s?\n" +
        r"Duration: (\d+\.?\d*)\s*seconds", 
        re.IGNORECASE
    )
    matches = pattern.findall(text)
    if matches:
        logger.info(f"Fallback parser: Found {len(matches)} segments using regex.")
        for match in matches:
            # This part would need robust time conversion if hh:mm:ss format is present
            # For now, assuming seconds if simple float/int, otherwise needs more logic
            try:
                start_time = float(match[2]) if '.' in match[2] else sum(x * int(t) for x, t in zip([3600, 60, 1], match[2].split(':')) if t.isdigit()) 
                end_time = float(match[3]) if '.' in match[3] else sum(x * int(t) for x, t in zip([3600, 60, 1], match[3].split(':')) if t.isdigit())
                segments.append({
                    "yt_title": match[1].strip(),
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": float(match[4]),
                    "hook": "Hook not extracted by regex", # Placeholder
                    "description": match[0].strip(), # Using subtopic as description
                    "platforms": ["TikTok", "YouTube_Shorts", "Instagram_Reels"], # Default
                    "hashtags": [] # Default
                })
            except ValueError as e:
                logger.warning(f"Fallback regex parser: Error converting times for match {match}: {e}")
                continue
    
    if not segments:
        logger.info("Fallback regex parsing failed or found no segments. Trying simpler manual parsing.")
        segments = _parse_segments_manually(text)

    if segments:
        return {"segments": segments}
    
    logger.error("Fallback text parsing failed to extract any segments.")
    return None

def call_openrouter_api(messages: List[Dict[str, str]], model: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Calls the OpenRouter API and returns the parsed JSON response."""
    if not config.OPENROUTER_API_KEY:
        logger.error("OpenRouter API key is not configured.")
        print("Error: OPENROUTER_API_KEY not set. Please check your .env file and config.py.", file=sys.stderr)
        return None

    api_model = model if model else config.OPENROUTER_MODEL
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost", # Optional, but good practice
        "X-Title": "YT Viral Clip Finder" # Optional
    }
    body = {
        "model": api_model,
        "messages": messages,
        "stream": False # Ensure non-streaming for single JSON response
    }

    logger.info(f"Calling OpenRouter API. Model: {api_model}. Messages: {json.dumps(messages, indent=2)[:500]}...") # Log truncated messages
    try:
        response = requests.post(
            f"{config.OPENROUTER_BASE_URL}/chat/completions", 
            headers=headers, 
            json=body, 
            timeout=300 # Increased timeout for potentially long analyses
        )
        response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
        
        response_data = response.json() # Parse the entire API response
        logger.debug(f"Full API response JSON: {json.dumps(response_data, indent=2)[:1000]}...")

        # Extract the actual content string, usually nested
        actual_content_string = ""
        if response_data.get("choices") and isinstance(response_data["choices"], list) and response_data["choices"]:
            first_choice = response_data["choices"][0]
            if first_choice.get("message") and first_choice["message"].get("content"):
                actual_content_string = first_choice["message"]["content"]
                logger.info("Extracted content string from API response choices.")
            else:
                logger.error("Could not find 'content' in API response message.")
                return None # Or attempt fallback with response.text if applicable
        else:
            logger.error("API response missing 'choices' or 'choices' is empty.")
            return None # Or attempt fallback

        logger.debug(f"Extracted content string (pre-cleaning): {actual_content_string[:500]}...")

        # Clean the extracted content string (e.g., remove markdown backticks)
        content_to_parse = actual_content_string
        json_match = re.search(r'```(?:json)?\n(.*?)\n```', actual_content_string, re.DOTALL | re.IGNORECASE)
        if json_match:
            logger.info("Found JSON block wrapped in triple backticks. Extracting content.")
            content_to_parse = json_match.group(1).strip()
        else:
            content_to_parse = actual_content_string.strip()
            # Check if it looks like JSON, if not, it might be plain text needing fallback
            if not (content_to_parse.startswith('{') and content_to_parse.endswith('}')) and \
               not (content_to_parse.startswith('[') and content_to_parse.endswith(']')):
                logger.warning("Cleaned content does not appear to be a standalone JSON object. Attempting fallback text parsing.")
                return parse_ai_text_response(actual_content_string) # Pass original extracted string to fallback

        logger.debug(f"Content string to parse as JSON: {content_to_parse[:500]}...")
        try:
            parsed_json_payload = json.loads(content_to_parse)
            logger.info("Successfully parsed the extracted content string as JSON.")
            return parsed_json_payload
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode the extracted content string as JSON: {e}. Content was: {content_to_parse[:500]}...")
            # Fallback to text parsing if JSON decoding of the cleaned string fails
            return parse_ai_text_response(actual_content_string) # Pass original extracted string

    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling OpenRouter API: {e}")
        print(f"API Request Error: {e}", file=sys.stderr)
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred in call_openrouter_api: {e}")
        return None

def analyze_transcript(transcript_text: str, model: Optional[str] = None) -> Optional[VideoTranscript]:
    """Analyzes transcript text to identify viral segments using AI."""
    if not transcript_text:
        logger.warning("analyze_transcript called with empty transcript_text.")
        return None

    messages = build_ai_prompt(transcript_text)
    api_response_data = call_openrouter_api(messages, model if model else config.OPENROUTER_MODEL)

    if not api_response_data:
        logger.error("No response data from API call in analyze_transcript.")
        return None

    if 'segments' not in api_response_data or not isinstance(api_response_data['segments'], list):
        logger.error(f"API response is missing 'segments' list or it's not a list. Data: {api_response_data}")
        # Attempt a final fallback if the structure is completely off but we got some text
        if isinstance(api_response_data, str): # If call_openrouter_api returned raw string due to some error
            logger.info("API response was a string, attempting text parse one last time.")
            fallback_data = parse_ai_text_response(api_response_data)
            if fallback_data and 'segments' in fallback_data:
                api_response_data = fallback_data
            else:
                return None
        else:
             return None # Cannot proceed if segments key is missing or malformed

    try:
        # Validate with Pydantic
        video_transcript = VideoTranscript(segments=api_response_data['segments'])
        logger.info(f"Successfully validated {len(video_transcript.segments)} segments using Pydantic.")
        return video_transcript
    except ValidationError as e:
        logger.error(f"Pydantic validation error for AI response: {e}. Data: {json.dumps(api_response_data['segments'], indent=2)}")
        # If Pydantic fails, we might still have usable data from manual parsing if it went through that route
        # The `parse_ai_text_response` already tries to structure it like `Segment`s
        # So, we can try to manually create `Segment` objects from its output if Pydantic fails here on the structured list.
        # This provides a last-ditch effort to salvage partially correct data.
        
        salvaged_segments = []
        for seg_data in api_response_data.get('segments', []):
            try:
                # Ensure essential fields are present before trying to create a Segment
                # This is a simplified check; more robust checks might be needed
                if all(k in seg_data for k in ['start_time', 'end_time', 'duration', 'yt_title', 'hook', 'description']):
                    salvaged_segments.append(Segment(**seg_data)) # Pydantic will raise error if types are wrong
                else:
                    logger.warning(f"Skipping segment due to missing essential fields during salvage: {seg_data}") 
            except Exception as pydantic_ex:
                logger.warning(f"Could not salvage segment {seg_data} due to Pydantic error: {pydantic_ex}")
        
        if salvaged_segments:
            logger.info(f"Salvaged {len(salvaged_segments)} segments after initial Pydantic validation failure.")
            return VideoTranscript(segments=salvaged_segments)
        else:
            logger.error("Could not salvage any segments after Pydantic validation failure.")
            return None
    except Exception as e:
        logger.error(f"Unexpected error during Pydantic validation or salvage: {e}")
        return None
