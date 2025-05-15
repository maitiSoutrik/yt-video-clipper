import os
import subprocess
import logging
import sys
from typing import List, Dict, Optional, Any

import config # For CLIPS_DIR

logger = logging.getLogger(__name__)

_ffmpeg_checked = False
_ffmpeg_present = False

def check_ffmpeg_installed() -> bool:
    """Checks if ffmpeg is installed and accessible in PATH. Caches result."""
    global _ffmpeg_checked, _ffmpeg_present
    if _ffmpeg_checked:
        return _ffmpeg_present
    
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
        logger.info(f"FFmpeg found: {result.stdout.splitlines()[0]}")
        _ffmpeg_present = True
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.error(f"FFmpeg is not installed or not found in PATH. Error: {e}")
        print("Error: FFmpeg is not installed or not found in your PATH. Video clipping will fail.", file=sys.stderr)
        print("Please install FFmpeg: https://ffmpeg.org/download.html", file=sys.stderr)
        _ffmpeg_present = False
    except Exception as e:
        logger.error(f"An unexpected error occurred while checking for FFmpeg: {e}")
        _ffmpeg_present = False
    
    _ffmpeg_checked = True
    return _ffmpeg_present

def generate_clip(
    input_video_path: str, 
    segment_data: Dict[str, Any], 
    output_base_dir: str,
    safe_video_title: str, 
    segment_index: int
) -> Optional[str]:
    """
    Generates a single video clip using ffmpeg.
    Returns the path to the generated clip, or None on failure.
    """
    global _ffmpeg_checked, _ffmpeg_present # Declare intent to use and potentially modify globals

    if not os.path.exists(input_video_path):
        logger.error(f"Input video path does not exist: {input_video_path}")
        return None

    # Defensive check, though generate_all_clips should call check_ffmpeg_installed first.
    # This check is now more robust due to the global declaration.
    if not _ffmpeg_checked:
        logger.info("generate_clip: _ffmpeg_checked is False, calling check_ffmpeg_installed().")
        check_ffmpeg_installed() # This will set the global _ffmpeg_checked and _ffmpeg_present
    
    if not _ffmpeg_present:
        logger.warning("FFmpeg not available (checked within generate_clip), cannot generate clip.")
        return None

    start_time = segment_data.get('start_time')
    end_time = segment_data.get('end_time')

    if start_time is None or end_time is None:
        logger.error(f"Segment {segment_index + 1} is missing start_time or end_time. Data: {segment_data}")
        return None
    
    if not os.path.exists(output_base_dir):
        try:
            os.makedirs(output_base_dir, exist_ok=True)
        except OSError as e:
            logger.error(f"Could not create output directory {output_base_dir}: {e}")
            return None

    output_filename = f"{safe_video_title}_clip_{segment_index + 1}.mp4"
    output_filepath = os.path.join(output_base_dir, output_filename)
    
    command = [
        "ffmpeg",
        "-i", input_video_path,
        "-ss", str(start_time),
        "-to", str(end_time),
        "-c:v", "libx264",
        "-preset", "slow", 
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        "-y", # Overwrite output files without asking
        "-loglevel", "error", # Reduce ffmpeg verbosity, log errors only
        output_filepath
    ]

    logger.info(f"Generating clip for segment {segment_index + 1}: {output_filepath}")
    logger.debug(f"FFmpeg command: {' '.join(command)}")

    try:
        process = subprocess.run(command, capture_output=True, text=True, check=False)
        
        if process.returncode != 0:
            logger.error(f"FFmpeg failed for segment {segment_index + 1} (file: {output_filepath}).")
            # FFmpeg errors are usually in stderr
            if process.stderr:
                logger.error(f"FFmpeg stderr: {process.stderr.strip()}")
            if process.stdout: # Some info might be in stdout too
                 logger.error(f"FFmpeg stdout: {process.stdout.strip()}")
            if os.path.exists(output_filepath):
                try: os.remove(output_filepath)
                except OSError as e: logger.warning(f"Could not remove failed output file {output_filepath}: {e}")
            return None
        else:
            logger.info(f"Successfully generated clip: {output_filepath}")
            # Even on success, ffmpeg might print to stderr (e.g. version info, warnings)
            if process.stderr:
                 logger.debug(f"FFmpeg stderr (on success): {process.stderr.strip()}")
            return output_filepath
            
    except FileNotFoundError: 
        logger.error("FFmpeg command not found. This should have been caught by check_ffmpeg_installed.")
        _ffmpeg_present = False # Mark as not present if this somehow happens
        _ffmpeg_checked = True
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while generating clip {output_filepath}: {e}")
        return None

def generate_all_clips(
    input_video_path: str, 
    segments_data: List[Dict[str, Any]],
    safe_video_title: str
) -> List[Dict[str, Any]]:
    """
    Generates all video clips based on the list of segments.
    Returns the list of segment data, updated with 'output_clip_path' and 'clip_generation_status'.
    """
    if not segments_data:
        logger.info("No segments provided to generate_all_clips.")
        return []

    if not check_ffmpeg_installed():
        logger.error("FFmpeg not available. Cannot generate clips.")
        for segment in segments_data:
            segment['output_clip_path'] = None
            segment['clip_generation_status'] = "ffmpeg_not_found"
        return segments_data

    # Ensure base clips directory exists, as generate_clip might be called for various subdirs later by output_manager
    # but for now, generate_clip itself will output to config.CLIPS_DIR
    if not os.path.exists(config.CLIPS_DIR):
        try:
            os.makedirs(config.CLIPS_DIR, exist_ok=True)
            logger.info(f"Created base clips directory: {config.CLIPS_DIR}")
        except OSError as e:
            logger.error(f"Could not create base clips directory {config.CLIPS_DIR}: {e}")
            for segment in segments_data:
                segment['output_clip_path'] = None
                segment['clip_generation_status'] = "output_dir_creation_failed"
            return segments_data

    processed_segments_info = []
    for i, segment_info_orig in enumerate(segments_data):
        segment_info = segment_info_orig.copy() # Work on a copy
        logger.info(f"Processing clip {i+1}/{len(segments_data)}: {segment_info.get('yt_title', 'Untitled Segment')}")
        
        clip_path = generate_clip(
            input_video_path=input_video_path,
            segment_data=segment_info,
            output_base_dir=config.CLIPS_DIR, # Clips are initially generated here
            safe_video_title=safe_video_title,
            segment_index=i
        )
        
        if clip_path:
            segment_info['output_clip_path'] = clip_path
            segment_info['clip_generation_status'] = "success"
            print(f"Clip generated for segment {i+1}: {clip_path}")
        else:
            segment_info['output_clip_path'] = None
            segment_info['clip_generation_status'] = "failed"
            print(f"Failed to generate clip for segment {i+1}: {segment_info.get('yt_title', 'Untitled Segment')}")
        
        processed_segments_info.append(segment_info)
        
    return processed_segments_info
