# main.py (Orchestrator)
import os
import sys
import logging # Keep for direct logger access if needed

# Import from our modules
import config
from utils import setup_logging
from youtube_handler import (
    extract_youtube_video_id,
    download_youtube_video,
    get_transcript_with_fallback,
    transcript_to_text
)
from ai_analyzer import analyze_transcript
from video_processor import generate_all_clips
from output_manager import (
    create_output_directories,
    organize_clip_for_platforms,
    save_segment_metadata_txt,
    save_segments_json
)

def main_orchestrator():
    # 1. Setup Logging
    logger = setup_logging(log_dir=config.LOG_DIR, log_file_name="yt_clipper_main.log")
    logger.info("yt-video-clipper application started.")
    print("Logging configured. Check logs for details.")

    # 2. Get user input for YouTube URL
    youtube_url = input("Enter a YouTube URL: ")
    logger.info(f"User provided URL: {youtube_url}")

    if not youtube_url:
        logger.error("No YouTube URL provided by the user.")
        print("Error: No YouTube URL entered. Exiting.", file=sys.stderr)
        sys.exit(1)

    # 3. Extract Video ID
    video_id = extract_youtube_video_id(youtube_url)
    if not video_id:
        logger.error(f"Could not extract video ID from URL: {youtube_url}")
        print(f"Error: Could not extract a valid YouTube video ID from '{youtube_url}'. Please check the URL.", file=sys.stderr)
        sys.exit(1)
    logger.info(f"Extracted Video ID: {video_id}")
    print(f"Processing Video ID: {video_id}")

    # 4. Download Video
    download_result = download_youtube_video(video_id)
    if not download_result:
        logger.error(f"Failed to download video for ID: {video_id}")
        print(f"Error: Failed to download video for ID '{video_id}'. Check logs for details.", file=sys.stderr)
        sys.exit(1)
    
    video_title, downloaded_filepath, safe_video_title = download_result
    logger.info(f"Video '{video_title}' downloaded to '{downloaded_filepath}'. Safe title: '{safe_video_title}'")
    print(f"Video '{video_title}' downloaded successfully.")

    # 5. Get Transcript
    transcript_data, transcript_source = get_transcript_with_fallback(video_id)
    if not transcript_data:
        logger.error(f"Could not retrieve transcript for video ID: {video_id}")
        print(f"Error: Could not retrieve transcript for video '{video_title}'. Check logs or try a different video.", file=sys.stderr)
        sys.exit(1)
    logger.info(f"Transcript retrieved. Source: {transcript_source}. Length: {len(transcript_data)} segments.")
    print(f"Transcript received (Source: {transcript_source}).")

    # 6. Convert Transcript to Text
    transcript_text = transcript_to_text(transcript_data)
    if not transcript_text:
        logger.error(f"Transcript for {video_id} was empty after conversion to text.")
        print(f"Error: Transcript for video '{video_title}' is empty.", file=sys.stderr)
        sys.exit(1)
    logger.info(f"Transcript converted to text. Length: {len(transcript_text)} characters.")

    # 7. Analyze Transcript with AI
    print("Analyzing video transcript with AI to identify viral segments...")
    analyzed_video_data = analyze_transcript(transcript_text, model=config.OPENROUTER_MODEL)
    
    if not analyzed_video_data or not analyzed_video_data.segments:
        logger.error(f"AI analysis failed to return valid segments for video ID: {video_id}")
        print(f"Error: AI analysis did not yield any usable segments for '{video_title}'. Check logs.", file=sys.stderr)
        sys.exit(1)
    logger.info(f"AI analysis complete. Found {len(analyzed_video_data.segments)} potential clips for '{video_title}'.")
    print(f"AI analysis identified {len(analyzed_video_data.segments)} potential clips.")

    # 8. Create Output Directories
    if not create_output_directories(base_clip_dir=config.CLIPS_DIR, platforms=config.SUPPORTED_PLATFORMS):
        logger.error(f"Failed to create necessary output directories in {config.CLIPS_DIR}. Aborting clip generation.")
        print(f"Error: Could not create output directories. Please check permissions and logs.", file=sys.stderr)
        sys.exit(1)
    logger.info(f"Output directories ensured/created in '{config.CLIPS_DIR}'.")

    # 9. Generate All Clips
    segments_to_process = [segment.model_dump() for segment in analyzed_video_data.segments]

    print("Generating short-form video clips for each identified segment...")
    processed_segments_info = generate_all_clips(
        input_video_path=downloaded_filepath,
        segments_data=segments_to_process,
        safe_video_title=safe_video_title
    )
    
    if not processed_segments_info:
        logger.warning(f"No clips were processed or generated for video {video_title}.")
    else:
        logger.info(f"Clip generation process completed for {video_title}. Processed {len(processed_segments_info)} segments.")
        print(f"Clip generation process finished for '{video_title}'.")

    # 10. Organize Clips for Platforms
    successful_clips_count = 0
    for segment_info in processed_segments_info:
        if segment_info.get('clip_generation_status') == 'success' and segment_info.get('output_clip_path'):
            logger.info(f"Organizing clip: {segment_info['output_clip_path']} for platforms: {segment_info.get('platforms')}")
            organize_clip_for_platforms(
                base_clip_path=segment_info['output_clip_path'],
                segment_platforms=segment_info.get('platforms', config.SUPPORTED_PLATFORMS),
                base_clip_dir=config.CLIPS_DIR
            )
            successful_clips_count +=1
        else:
            logger.warning(f"Skipping organization for segment due to generation failure or no path: {segment_info.get('yt_title')}")
    
    logger.info(f"Successfully generated and organized {successful_clips_count} clips.")

    # 11. Save Segment Metadata (Text and JSON)
    metadata_txt_path = save_segment_metadata_txt(
        segments_data=processed_segments_info, 
        video_title=safe_video_title,
        base_clip_dir=config.CLIPS_DIR
    )
    if metadata_txt_path:
        logger.info(f"Segment metadata text file saved to: {metadata_txt_path}")
        print(f"Segment metadata (TXT) saved to: {metadata_txt_path}")
    else:
        logger.warning(f"Failed to save segment metadata text file for {safe_video_title}.")

    segments_json_path = save_segments_json(
        segments_data=processed_segments_info,
        video_title=safe_video_title,
        base_clip_dir=config.CLIPS_DIR
    )
    if segments_json_path:
        logger.info(f"Segment data JSON file saved to: {segments_json_path}")
        print(f"Segment data (JSON) saved to: {segments_json_path}")
    else:
        logger.warning(f"Failed to save segment data JSON file for {safe_video_title}.")

    # 12. Print Final Summary
    final_summary_message = (
        f"\\n--- Process Complete for '{video_title}' ---\\n"
        f"Video ID: {video_id}\\n"
        f"Downloaded Video: {downloaded_filepath}\\n"
        f"Identified {len(analyzed_video_data.segments)} potential clips from transcript.\\n"
        f"Successfully generated {successful_clips_count} video clips in '{config.CLIPS_DIR}'.\\n"
        f"Metadata saved to: {metadata_txt_path or 'Not saved'}\\n"
        f"Segment JSON data saved to: {segments_json_path or 'Not saved'}\\n"
        f"Please check the '{config.CLIPS_DIR}' directory and its subfolders for output."
    )
    logger.info(final_summary_message.replace('\\n', ' ')) # Log as single line
    print(final_summary_message)

if __name__ == "__main__":
    try:
        main_orchestrator()
    except Exception as e:
        main_logger = logging.getLogger(__name__) # Use a local logger instance for this block
        # Check if the root logger (or any relevant logger) has handlers before trying to log the critical error.
        # This prevents NoHandlerFound errors if setup_logging itself failed or wasn't called.
        if logging.getLogger().hasHandlers() or main_logger.hasHandlers(): # Check root or local
            main_logger.critical(f"An unhandled critical error occurred in main_orchestrator: {e}", exc_info=True)
        else: # Fallback to print if no loggers are configured
            print(f"CRITICAL ERROR (logging not configured): {e}", file=sys.stderr)
        
        print(f"An unexpected critical error occurred. Please check the logs or console output for details. Error: {e}", file=sys.stderr)
        sys.exit(1)
