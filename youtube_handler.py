import os
import re
import subprocess
import time
import logging
import sys
from typing import List, Dict, Any, Optional, Tuple
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

import config # For DOWNLOAD_DIR etc.

logger = logging.getLogger(__name__)

def extract_youtube_video_id(url: str) -> Optional[str]:
    """Extract the video ID from various YouTube URL formats."""
    standard_pattern = r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})(?:&|\?|$)'
    shorts_pattern = r'youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})(?:&|\?|$)'
    
    match = re.search(standard_pattern, url)
    if match:
        return match.group(1)
    
    match = re.search(shorts_pattern, url)
    if match:
        return match.group(1)
    
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
        return url
    
    logger.error(f"Could not extract video ID from URL: {url}")
    return None

def download_youtube_video(video_id: str, max_retries: int = 3) -> Optional[Tuple[str, str, str]]:
    """
    Download a YouTube video using yt-dlp.
    Returns a tuple of (video_title, filename, safe_video_title) on success or None on failure.
    """
    if not video_id:
        logger.error("No video_id provided to download_youtube_video.")
        return None

    clean_youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    logger.info(f"Attempting to download video with yt-dlp: {clean_youtube_url}")

    if not os.path.exists(config.DOWNLOAD_DIR):
        os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)

    try:
        subprocess.run(["yt-dlp", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.error("yt-dlp is not installed or not found in PATH.")
        print("Error: yt-dlp is not installed. Please install it (e.g., pip install yt-dlp) and ensure it's in your PATH.", file=sys.stderr)
        return None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Download attempt {attempt}/{max_retries} for {video_id}")
            print(f"Downloading video {video_id} (attempt {attempt}/{max_retries})...")

            cmd_info = [
                "yt-dlp",
                clean_youtube_url,
                "--print", "%(title)s#%(release_date)s#%(id)s", # Get title, release_date, and id
                "--no-warnings",
                "--no-playlist",
                "--skip-download" # Only get info first
            ]
            result_info = subprocess.run(cmd_info, capture_output=True, text=True, check=False)

            if result_info.returncode != 0:
                logger.error(f"Error getting video info for {video_id} (attempt {attempt}): {result_info.stderr.strip()}")
                if attempt < max_retries: time.sleep(2); continue
                return None

            video_details_str = result_info.stdout.strip()
            if '#' not in video_details_str:
                logger.error(f"Unexpected format from yt-dlp info for {video_id}: {video_details_str}")
                if attempt < max_retries: time.sleep(2); continue
                return None
            
            title_part, date_part, id_part = video_details_str.split('#', 2)
            video_title = title_part.strip()
            # release_date = date_part.strip() if date_part.strip() != "NA" else None # yt-dlp might return NA
            # fetched_video_id = id_part.strip()

            logger.info(f"Video title for {video_id}: {video_title}")
            safe_video_title = re.sub(r'[^\w\-_\.]', '_', video_title) # More robust safe title
            if not safe_video_title: safe_video_title = video_id # Fallback if title becomes empty
            
            filename = os.path.join(config.DOWNLOAD_DIR, f"{safe_video_title}.mp4")
            
            cmd_download = [
                "yt-dlp",
                clean_youtube_url,
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "-o", filename,
                "--no-warnings",
                "--no-playlist",
                "--progress"
            ]
            
            logger.info(f"Downloading video {video_id} with command: {' '.join(cmd_download)}")
            process = subprocess.Popen(cmd_download, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()

            if process.returncode == 0 and os.path.exists(filename):
                logger.info(f"Video {video_id} downloaded successfully: {filename}")
                print(f"Video '{video_title}' downloaded successfully as {filename}")
                return video_title, filename, safe_video_title
            else:
                logger.error(f"Error downloading video {video_id} (attempt {attempt}): {stderr.strip()}")
                if os.path.exists(filename): # Cleanup partial download if any
                    try: os.remove(filename)
                    except OSError: pass
                if attempt < max_retries: time.sleep(5); continue # Longer sleep for download errors
                return None

        except subprocess.CalledProcessError as e:
            logger.error(f"Subprocess error during download attempt {attempt} for {video_id}: {e}")
            if attempt < max_retries: time.sleep(5); continue
            return None
        except Exception as e:
            logger.error(f"Unexpected error during download attempt {attempt} for {video_id}: {e}")
            if attempt < max_retries: time.sleep(5); continue
            return None
    logger.error(f"Failed to download video {video_id} after {max_retries} retries.")
    return None

def _convert_fetched_transcript_to_list_of_dicts(fetched_data: Any, source_description_for_logging: str) -> List[Dict]:
    """
    Converts FetchedTranscript object (or similar structure) to a list of dictionaries.
    If input is already List[Dict], returns it. Otherwise, attempts conversion.
    """
    data_to_standardize = []
    if not fetched_data:
        logger.info(f"_convert_fetched_transcript: fetched_data for {source_description_for_logging} is None or empty. Returning empty list.")
        return []

    # Duck-typing for FetchedTranscript-like objects
    if hasattr(fetched_data, 'snippets') and isinstance(fetched_data.snippets, list):
        logger.info(f"_convert_fetched_transcript: Processing FetchedTranscript.snippets for {source_description_for_logging}...")
        for i, snippet_obj in enumerate(fetched_data.snippets):
            if hasattr(snippet_obj, 'text') and hasattr(snippet_obj, 'start') and hasattr(snippet_obj, 'duration'):
                data_to_standardize.append({
                    'text': snippet_obj.text,
                    'start': snippet_obj.start,
                    'duration': snippet_obj.duration
                })
            else:
                logger.warning(f"_convert_fetched_transcript: Snippet #{i} for {source_description_for_logging} is malformed: {str(snippet_obj)[:100]}. Skipping.")
        logger.info(f"_convert_fetched_transcript: Converted {len(data_to_standardize)} snippets to dicts for {source_description_for_logging}.")
    elif isinstance(fetched_data, list):
        is_list_of_dicts = True
        if fetched_data: # Check items only if list is not empty
            if not all(isinstance(item, dict) for item in fetched_data):
                is_list_of_dicts = False
                logger.warning(f"_convert_fetched_transcript: fetched_data for {source_description_for_logging} is a list, but not all items are dicts. First item type: {type(fetched_data[0]) if fetched_data else 'N/A'}.")
        
        if is_list_of_dicts:
            logger.info(f"_convert_fetched_transcript: fetched_data for {source_description_for_logging} is already a list of dicts ({len(fetched_data)} items). Using as is.")
            data_to_standardize = fetched_data
        else:
            logger.warning(f"_convert_fetched_transcript: fetched_data for {source_description_for_logging} is a list but not of dicts. Treating as empty.")
            # data_to_standardize remains []
    else:
        logger.warning(f"_convert_fetched_transcript: fetched_data for {source_description_for_logging} is of unexpected type: {type(fetched_data)}. Treating as empty list.")
        # data_to_standardize remains []
    return data_to_standardize

def get_available_transcript_languages(video_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """Get a list of available languages for a video's transcripts."""
    results = {'manual': [], 'generated': [], 'translatable_to_en': []}
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        for tx_info in transcript_list:
            lang_info = {
                'language': tx_info.language,
                'language_code': tx_info.language_code,
                'is_generated': tx_info.is_generated,
                'is_translatable': tx_info.is_translatable
            }
            if tx_info.is_generated:
                results['generated'].append(lang_info)
            else:
                results['manual'].append(lang_info)
            if tx_info.is_translatable and tx_info.language_code != 'en':
                results['translatable_to_en'].append(lang_info)
        logger.info(f"Available transcripts for {video_id}: {results}")
    except TranscriptsDisabled:
        logger.warning(f"Transcripts are disabled for video {video_id}")
    except NoTranscriptFound:
        logger.warning(f"No transcripts found for video {video_id}")
    except Exception as e:
        logger.error(f"Error fetching transcript list for {video_id}: {e}")
    return results

def get_transcript_with_fallback(video_id: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
    """
    Attempt to get a transcript with the following fallback strategy:
    1. Try English (manual first, then generated)
    2. Try any manually created transcript and translate to English
    3. Try any auto-generated transcript and translate to English
    Returns a tuple of (transcript_data, transcript_source_description).
    """
    def standardize_transcript(transcript_data: List[Dict]) -> List[Dict]:
        """Convert transcript to standard dictionary format if it's not already."""
        logger.info(f"standardize_transcript called. Input data type: {type(transcript_data)}")
        if isinstance(transcript_data, list):
            logger.info(f"standardize_transcript input is a list. Length: {len(transcript_data)}")
            if transcript_data: 
                 logger.info(f"First item of transcript_data (type {type(transcript_data[0])}): {str(transcript_data[0])[:200]}")
            else:
                 logger.info("standardize_transcript input list is empty.")
        else:
            logger.warning(f"standardize_transcript received non-list data: {str(transcript_data)[:200]}")

        if not transcript_data or not isinstance(transcript_data, list): # Handles None, empty list, or non-list
            logger.warning(f"standardize_transcript: input data is None, empty, or not a list. Actual data (first 100 chars): '{str(transcript_data)[:100]}'. Returning empty list.")
            return []
        
        standardized = []
        items_processed = 0
        items_skipped_malformed = 0
        items_skipped_missing_duration_logic = 0 # Renamed counter

        for i, item in enumerate(transcript_data):
            items_processed +=1
            if not isinstance(item, dict) or 'text' not in item or 'start' not in item:
                logger.warning(f"standardize_transcript: Skipping malformed transcript item #{i} (missing 'text' or 'start'): {str(item)[:200]}")
                items_skipped_malformed += 1
                continue
            
            current_duration = item.get('duration')
            current_end = item.get('end')
            current_start = item['start'] 

            if current_duration is None:
                if current_end is not None:
                    try:
                        # Ensure start and end are numbers before subtraction
                        start_f = float(current_start)
                        end_f = float(current_end)
                        item['duration'] = round(end_f - start_f, 2)
                        logger.info(f"standardize_transcript: Calculated duration for item #{i} as {item['duration']}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"standardize_transcript: Error calculating duration for item #{i} (start: {current_start}, end: {current_end}): {e}. Using default 0.0. Item: {str(item)[:200]}")
                        item['duration'] = 0.0 
                        items_skipped_missing_duration_logic +=1 
                else:
                    logger.warning(f"standardize_transcript: Transcript item #{i} missing duration and end time. Using default duration 0.0. Item: {str(item)[:200]}")
                    item['duration'] = 0.0
                    items_skipped_missing_duration_logic +=1
            
            try:
                # Ensure start and duration are numbers before float conversion and rounding
                start_val = round(float(item['start']), 2)
                duration_val = round(float(item['duration']), 2)
            except (ValueError, TypeError) as e:
                logger.warning(f"standardize_transcript: Could not convert start/duration to float for item #{i}. Skipping. Error: {e}. Item: {str(item)[:200]}")
                items_skipped_malformed +=1 
                continue

            standardized.append({
                'text': item['text'],
                'start': start_val,
                'duration': duration_val
            })
        
        logger.info(f"standardize_transcript summary: Total items processed: {items_processed}, Standardized: {len(standardized)}, Skipped (malformed/type error): {items_skipped_malformed}, Skipped (duration logic issues): {items_skipped_missing_duration_logic}.")
        return standardized

    logger.info(f"Attempting to fetch transcript for video ID: {video_id}")
    available_langs = get_available_transcript_languages(video_id)

    # Priority 1: English (manual then generated)
    for lang_code in ['en', 'en-US', 'en-GB']:
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            # Try manual first
            manual_en_transcript = next((t for t in transcript_list if t.language_code == lang_code and not t.is_generated), None)
            if manual_en_transcript:
                logger.info(f"Found manual English transcript object for ({lang_code}). Type: {type(manual_en_transcript)}")
                fetched_data = None
                try:
                    logger.info(f"Attempting to .fetch() manual English transcript for {lang_code}...")
                    fetched_data = manual_en_transcript.fetch()
                    logger.info(f".fetch() for manual {lang_code} successful. Type of fetched_data: {type(fetched_data)}")
                    if isinstance(fetched_data, list):
                        logger.info(f"Fetched_data is a list with {len(fetched_data)} segments for manual {lang_code}.")
                        if not fetched_data: logger.warning(f"Manual {lang_code} .fetch() returned an EMPTY list.")
                        elif fetched_data: logger.info(f"First segment from manual {lang_code} .fetch(): {str(fetched_data[0])[:200]}")
                    else: logger.warning(f"Manual {lang_code} .fetch() did NOT return a list. Data: {str(fetched_data)[:200]}")
                except Exception as fetch_exc:
                    logger.error(f"Exception during .fetch() for manual {lang_code}: {fetch_exc}", exc_info=True)
                    continue # Try next lang_code or fallback

                logger.info(f"Proceeding to convert and standardize for manual {lang_code}.")
                list_to_standardize = _convert_fetched_transcript_to_list_of_dicts(fetched_data, f"manual {lang_code}")
                standardized_result = standardize_transcript(list_to_standardize)
                
                if not standardized_result and list_to_standardize: # Log if conversion + standardization led to empty from non-empty
                    logger.warning(f"Standardization of manual {lang_code} resulted in empty list from non-empty input.")
                elif not standardized_result:
                    logger.warning(f"Standardization of manual {lang_code} resulted in empty/None.")
                else:
                    logger.info(f"Standardization of manual {lang_code} returned {len(standardized_result)} segments.")
                return standardized_result, f"English ({lang_code}, manual)"

            # Try generated
            generated_en_transcript = next((t for t in transcript_list if t.language_code == lang_code and t.is_generated), None)
            if generated_en_transcript:
                logger.info(f"Found auto-generated English transcript object for ({lang_code}). Type: {type(generated_en_transcript)}")
                fetched_data = None
                try:
                    logger.info(f"Attempting to .fetch() auto-generated English transcript for {lang_code}...")
                    fetched_data = generated_en_transcript.fetch()
                    logger.info(f".fetch() for auto-generated {lang_code} successful. Type of fetched_data: {type(fetched_data)}")
                    if fetched_data and hasattr(fetched_data, 'snippets') and isinstance(fetched_data.snippets, list):
                         logger.info(f"Fetched_data for auto-generated {lang_code} has {len(fetched_data.snippets)} snippets. First snippet (if any): {str(fetched_data.snippets[0])[:200] if fetched_data.snippets else 'N/A'}")
                    elif isinstance(fetched_data, list):
                        logger.info(f"Fetched_data for auto-generated {lang_code} is a list with {len(fetched_data)} segments. First segment (if any): {str(fetched_data[0])[:200] if fetched_data else 'N/A'}")
                    else:
                        logger.warning(f"Auto-generated {lang_code} .fetch() returned unexpected data type or empty. Data: {str(fetched_data)[:200]}")

                except Exception as fetch_exc:
                    logger.error(f"Exception during .fetch() for auto-generated {lang_code}: {fetch_exc}", exc_info=True)
                    continue # Try next lang_code or fallback
                
                logger.info(f"Proceeding to convert and standardize for auto-generated {lang_code}.")
                list_to_standardize = _convert_fetched_transcript_to_list_of_dicts(fetched_data, f"auto-generated {lang_code}")
                standardized_result = standardize_transcript(list_to_standardize)

                if not standardized_result and list_to_standardize:
                     logger.warning(f"Standardization of auto-generated {lang_code} resulted in empty list from non-empty input.")
                elif not standardized_result:
                    logger.warning(f"Standardization of auto-generated {lang_code} resulted in empty/None.")
                else:
                    logger.info(f"Standardization of auto-generated {lang_code} returned {len(standardized_result)} segments.")
                return standardized_result, f"English ({lang_code}, auto-generated)"
        except NoTranscriptFound:
            logger.info(f"No transcript found for English variant {lang_code} via YouTubeTranscriptApi.list_transcripts().")
            continue # Try next English variant
        except Exception as e:
            logger.error(f"Error processing English transcript ({lang_code}): {e}", exc_info=True)
            # This will catch errors from list_transcripts or other unexpected issues within the try block for this lang_code
            continue # Try next English variant or fallback

    # Priority 2: Any other manual transcript, translated to English
    if available_langs['manual']:
        for lang_info in available_langs['manual']:
            if lang_info['language_code'] == 'en': continue # Already tried
            if lang_info['is_translatable']:
                try:
                    logger.info(f"Trying manual transcript in {lang_info['language']} ({lang_info['language_code']}), will translate to English")
                    transcript_obj = YouTubeTranscriptApi.list_transcripts(video_id).find_manually_created_transcript([lang_info['language_code']])
                    translated_transcript_obj = transcript_obj.translate('en')
                    fetched_translated_data = translated_transcript_obj.fetch()
                    
                    source_desc = f"{lang_info['language']} (manual, translated to en)"
                    list_to_standardize = _convert_fetched_transcript_to_list_of_dicts(fetched_translated_data, source_desc)
                    standardized_result = standardize_transcript(list_to_standardize)
                    
                    if standardized_result:
                        logger.info(f"Successfully processed: {source_desc}")
                        return standardized_result, source_desc
                    else:
                        logger.warning(f"Failed to standardize after fetching/converting: {source_desc}")

                except Exception as e:
                    logger.error(f"Error translating manual {lang_info['language']} transcript: {e}", exc_info=True)
    
    # Priority 3: Any other auto-generated transcript, translated to English
    if available_langs['generated']:
        for lang_info in available_langs['generated']:
            if lang_info['language_code'].startswith('en'): continue # Already tried
            if lang_info['is_translatable']:
                try:
                    logger.info(f"Trying auto-generated transcript in {lang_info['language']} ({lang_info['language_code']}), will translate to English")
                    transcript_obj = YouTubeTranscriptApi.list_transcripts(video_id).find_generated_transcript([lang_info['language_code']])
                    translated_transcript_obj = transcript_obj.translate('en')
                    fetched_translated_data = translated_transcript_obj.fetch()

                    source_desc = f"{lang_info['language']} (auto-generated, translated to en)"
                    list_to_standardize = _convert_fetched_transcript_to_list_of_dicts(fetched_translated_data, source_desc)
                    standardized_result = standardize_transcript(list_to_standardize)

                    if standardized_result:
                        logger.info(f"Successfully processed: {source_desc}")
                        return standardized_result, source_desc
                    else:
                        logger.warning(f"Failed to standardize after fetching/converting: {source_desc}")
                        
                except Exception as e:
                    logger.error(f"Error translating auto-generated {lang_info['language']} transcript: {e}", exc_info=True)

    logger.warning(f"Could not retrieve or translate any transcript for video {video_id}.")
    return None, None

def transcript_to_text(transcript_data: List[Dict]) -> str:
    """Convert transcript data to simple text format for the prompt."""
    if not transcript_data:
        return ""
    return " ".join([item['text'] for item in transcript_data if 'text' in item])
