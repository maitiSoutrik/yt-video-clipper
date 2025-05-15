import os
import json
import logging
import sys
import shutil # For copying files if symlinking fails
from typing import List, Dict, Any, Optional

import config # For CLIPS_DIR, SUPPORTED_PLATFORMS

logger = logging.getLogger(__name__)

def create_output_directories(
    base_clip_dir: Optional[str] = None, 
    platforms: Optional[List[str]] = None
) -> bool:
    """
    Creates the base output directory and platform-specific subdirectories.
    Uses defaults from config if parameters are None.
    Returns True on success, False on failure to create a crucial directory.
    """
    active_base_clip_dir = base_clip_dir if base_clip_dir else config.CLIPS_DIR
    active_platforms = platforms if platforms else config.SUPPORTED_PLATFORMS

    try:
        os.makedirs(active_base_clip_dir, exist_ok=True)
        logger.info(f"Ensured base output directory exists: {active_base_clip_dir}")
    except OSError as e:
        logger.error(f"Failed to create base output directory {active_base_clip_dir}: {e}")
        print(f"Error: Could not create base directory {active_base_clip_dir}. Check permissions.", file=sys.stderr)
        return False

    for platform in active_platforms:
        platform_dir = os.path.join(active_base_clip_dir, platform)
        try:
            os.makedirs(platform_dir, exist_ok=True)
            logger.info(f"Ensured platform directory exists: {platform_dir}")
        except OSError as e:
            # Log error but don't necessarily fail all if one platform dir fails, though it's a problem.
            logger.error(f"Failed to create platform directory {platform_dir}: {e}")
            # Depending on strictness, you might want to return False here too.
    return True

def organize_clip_for_platforms(
    base_clip_path: str, 
    segment_platforms: List[str], 
    base_clip_dir: Optional[str] = None
) -> List[str]:
    """
    Organizes a generated clip into specified platform subdirectories using symlinks (or copies as fallback).
    Returns a list of paths where the clip was successfully placed/linked.
    """
    if not os.path.exists(base_clip_path):
        logger.error(f"Base clip path does not exist, cannot organize: {base_clip_path}")
        return []

    active_base_clip_dir = base_clip_dir if base_clip_dir else config.CLIPS_DIR
    organized_paths = []

    # Use all supported platforms if segment_platforms is empty or None
    target_platforms = segment_platforms if segment_platforms else config.SUPPORTED_PLATFORMS

    for platform in target_platforms:
        platform_dir = os.path.join(active_base_clip_dir, platform)
        if not os.path.exists(platform_dir):
            logger.warning(f"Platform directory {platform_dir} does not exist. Attempting to create.")
            try:
                os.makedirs(platform_dir, exist_ok=True)
            except OSError as e:
                logger.error(f"Could not create missing platform directory {platform_dir} for organizing: {e}")
                continue # Skip this platform
        
        clip_filename = os.path.basename(base_clip_path)
        platform_specific_path = os.path.join(platform_dir, clip_filename)

        if os.path.exists(platform_specific_path) or os.path.islink(platform_specific_path):
            logger.info(f"Clip already exists or linked at {platform_specific_path} for platform {platform}. Skipping.")
            organized_paths.append(platform_specific_path)
            continue

        try:
            # Attempt to create a relative symlink
            # Symlink target path should be relative from the link's directory to the actual file
            relative_target_path = os.path.relpath(base_clip_path, start=platform_dir)
            os.symlink(relative_target_path, platform_specific_path)
            logger.info(f"Successfully symlinked clip to {platform_specific_path} (target: {relative_target_path})")
            organized_paths.append(platform_specific_path)
        except OSError as e_symlink: # Symlinking might fail (e.g., on Windows without admin rights)
            logger.warning(f"Symlinking failed for {platform_specific_path} (target: {relative_target_path}): {e_symlink}. Attempting to copy instead.")
            try:
                shutil.copy2(base_clip_path, platform_specific_path)
                logger.info(f"Successfully copied clip to {platform_specific_path}")
                organized_paths.append(platform_specific_path)
            except Exception as e_copy:
                logger.error(f"Failed to copy clip to {platform_specific_path}: {e_copy}")
        except Exception as e_general:
            logger.error(f"An unexpected error occurred while organizing clip for {platform}: {e_general}")
            
    return organized_paths

def save_segment_metadata_txt(
    segments_data: List[Dict[str, Any]], 
    video_title: str, 
    base_clip_dir: Optional[str] = None
) -> Optional[str]:
    """
    Saves human-readable metadata for all processed segments to a text file.
    Returns the path to the metadata file, or None on failure.
    """
    if not segments_data:
        logger.info("No segment data to save to text metadata.")
        return None

    active_base_clip_dir = base_clip_dir if base_clip_dir else config.CLIPS_DIR
    filepath = os.path.join(active_base_clip_dir, f"{video_title}_segment_metadata.txt")

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"Video Title: {video_title}\n")
            f.write(f"Total Segments Found: {len(segments_data)}\n\n")
            for i, segment in enumerate(segments_data):
                f.write(f"--- Segment {i + 1} ---\n")
                f.write(f"  Title: {segment.get('yt_title', 'N/A')}\n")
                f.write(f"  Start Time: {segment.get('start_time', 'N/A')}s\n")
                f.write(f"  End Time: {segment.get('end_time', 'N/A')}s\n")
                f.write(f"  Duration: {segment.get('duration', 'N/A')}s\n")
                f.write(f"  Hook: {segment.get('hook', 'N/A')}\n")
                f.write(f"  Description: {segment.get('description', 'N/A')}\n")
                platforms_str = ", ".join(segment.get('platforms', [])) or "N/A"
                f.write(f"  Recommended Platforms: {platforms_str}\n")
                hashtags_str = " ".join(segment.get('hashtags', [])) or "N/A"
                f.write(f"  Hashtags: {hashtags_str}\n")
                f.write(f"  Clip Generation Status: {segment.get('clip_generation_status', 'Unknown')}\n")
                f.write(f"  Output Clip Path: {segment.get('output_clip_path', 'N/A')}\n\n")
        logger.info(f"Segment metadata saved to: {filepath}")
        return filepath
    except IOError as e:
        logger.error(f"Failed to write segment metadata to {filepath}: {e}")
        print(f"Error: Could not save metadata file {filepath}. Check permissions.", file=sys.stderr)
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while saving segment metadata: {e}")
        return None

def save_segments_json(
    segments_data: List[Dict[str, Any]], 
    video_title: str,
    base_clip_dir: Optional[str] = None
) -> Optional[str]:
    """
    Saves the structured segment data (often from AI analysis, enriched with processing info)
    to a JSON file.
    Returns the path to the JSON file, or None on failure.
    """
    if not segments_data:
        logger.info("No segment data to save to JSON.")
        return None

    active_base_clip_dir = base_clip_dir if base_clip_dir else config.CLIPS_DIR
    filepath = os.path.join(active_base_clip_dir, f"{video_title}_segments_data.json")
    
    output_data = {
        "video_title": video_title,
        "total_segments": len(segments_data),
        "segments": segments_data 
    }

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=4, ensure_ascii=False)
        logger.info(f"Segment data saved to JSON: {filepath}")
        return filepath
    except IOError as e:
        logger.error(f"Failed to write segment data to JSON {filepath}: {e}")
        print(f"Error: Could not save JSON file {filepath}. Check permissions.", file=sys.stderr)
        return None
    except TypeError as e: # Handle potential non-serializable data if not careful
        logger.error(f"TypeError during JSON serialization for {filepath}: {e}. Ensure all data is serializable.")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while saving segments JSON: {e}")
        return None

if __name__ == '__main__':
    # Example Usage (for testing this module independently)
    print("Testing Output Manager...")
    
    # Ensure logger is set up for standalone testing
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s', stream=sys.stdout)

    # Use a temporary directory for testing
    test_output_dir = os.path.join(config.BASE_DIR, "test_generated_clips") 
    if not os.path.exists(test_output_dir):
        os.makedirs(test_output_dir, exist_ok=True)

    # 1. Test create_output_directories
    print("\nTesting create_output_directories...")
    success = create_output_directories(base_clip_dir=test_output_dir, platforms=["TestPlatform1", "TestPlatform2"])
    print(f"create_output_directories success: {success}")
    if success:
        assert os.path.exists(os.path.join(test_output_dir, "TestPlatform1"))
        assert os.path.exists(os.path.join(test_output_dir, "TestPlatform2"))
        print("Directory creation verified.")

    # 2. Test organize_clip_for_platforms (requires a dummy clip)
    print("\nTesting organize_clip_for_platforms...")
    dummy_clip_name = "dummy_test_clip.mp4"
    dummy_clip_path = os.path.join(test_output_dir, dummy_clip_name)
    with open(dummy_clip_path, 'w') as f: f.write("dummy content") # Create dummy file
    
    organized_paths = organize_clip_for_platforms(dummy_clip_path, ["TestPlatform1"], base_clip_dir=test_output_dir)
    print(f"Organized paths: {organized_paths}")
    if organized_paths:
        assert os.path.exists(os.path.join(test_output_dir, "TestPlatform1", dummy_clip_name))
        print("Clip organization verified.")
    os.remove(dummy_clip_path) # Clean up dummy clip

    # 3. Test save_segment_metadata_txt and save_segments_json
    print("\nTesting metadata and JSON saving...")
    sample_segments_data = [
        {
            'yt_title': 'First Awesome Clip', 'start_time': 0.0, 'end_time': 10.0, 'duration': 10.0,
            'hook': 'Intro hook', 'description': 'Desc 1', 'platforms': ['TestPlatform1'], 'hashtags': ['#test1'],
            'clip_generation_status': 'success', 'output_clip_path': os.path.join(test_output_dir, "TestPlatform1", dummy_clip_name)
        },
        {
            'yt_title': 'Second Cool Segment', 'start_time': 15.0, 'end_time': 30.0, 'duration': 15.0,
            'hook': 'Another hook', 'description': 'Desc 2', 'platforms': ['TestPlatform2'], 'hashtags': ['#test2'],
            'clip_generation_status': 'failed', 'output_clip_path': None
        }
    ]
    txt_path = save_segment_metadata_txt(sample_segments_data, "MyTestVideo", base_clip_dir=test_output_dir)
    json_path = save_segments_json(sample_segments_data, "MyTestVideo", base_clip_dir=test_output_dir)
    print(f"Metadata TXT saved to: {txt_path}")
    print(f"Segments JSON saved to: {json_path}")
    if txt_path: assert os.path.exists(txt_path)
    if json_path: assert os.path.exists(json_path)
    print("Metadata and JSON saving verified.")

    print("\n--- Output Manager Test Complete ---")
    # Consider removing test_output_dir after tests if desired, e.g., shutil.rmtree(test_output_dir)
