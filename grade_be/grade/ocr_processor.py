import os
import json
import logging
from .ocr_processing_core import (
    extract_images_from_pdf,
    images_to_pdf_bytes,
    gemini_json_from_pdf,
    detect_and_crop_diagrams,
    save_ocr_metrics_csv,
    print_ocr_metrics_summary,
    save_ocr_metrics_to_db,  # NEW: Save metrics to DB
    scan_all_pages_batch,   # Use the batch function
    smart_crop_content,     # Use the content cropping function
    PageScanBatchResult,    # Import the new batch schema
)

logger = logging.getLogger(__name__)


# def process_answer_ocr(file_path, output_json_dir, output_images_dir, user_id):
#     """
#     Process uploaded answer file with OCR and return results

#     Args:
#         file_path: Path to the uploaded PDF file
#         output_json_dir: Directory to store JSON results
#         output_images_dir: Directory to store diagram images
#         user_id: ID of the user who uploaded the file

#     Returns:
#         dict: Result with success status, paths, and any errors
#     """
#     try:
#         logger.info(f"Starting OCR processing for file: {file_path}")

#         # Step 1: Extract images from PDF
#         logger.info("Step 1: Extracting images from PDF...")
#         all_images = extract_images_from_pdf(file_path)

#         if not all_images:
#             return {
#                 "success": False,
#                 "error": "No images could be extracted from the PDF",
#             }

#         logger.info(f"Extracted {len(all_images)} images")

#         # Step 2: Group by roll number and sort by page
#         logger.info("Step 2: Grouping images by roll number...")
#         grouped_images = group_by_and_sort_by_page(all_images)

#         if not grouped_images:
#             return {
#                 "success": False,
#                 "error": "No valid roll numbers found in the images",
#             }

#         # Process each roll number group
#         results = {}

#         for roll_number, pages_data in grouped_images.items():
#             logger.info(f"Processing roll number: {roll_number}")

#             try:
#                 # Sort by page number and extract images
#                 sorted_images = [img for _, img, _ in pages_data]

#                 # Step 3: Convert images to PDF for Gemini processing
#                 pdf_bytes = images_to_pdf_bytes(sorted_images)

#                 if not pdf_bytes:
#                     logger.warning(
#                         f"Could not create PDF for roll {roll_number}"
#                     )
#                     continue

#                 # Step 4: Extract JSON from PDF using Gemini
#                 logger.info(f"Extracting JSON for roll {roll_number}...")
#                 raw_json = gemini_json_from_pdf(
#                     pdf_bytes, output_images_dir, roll_number
#                 )

#                 # Step 5: Convert and validate JSON format
#                 formatted_json = convert_answers_format(raw_json)

#                 # Step 6: Detect and crop diagrams
#                 logger.info(f"Processing diagrams for roll {roll_number}...")
#                 final_json = detect_and_crop_diagrams(
#                     sorted_images,
#                     formatted_json,
#                     output_images_dir,
#                     roll_number,
#                 )

#                 # Step 7: Save JSON file
#                 json_filename = f"{roll_number}_{user_id}_answers.json"
#                 json_path = os.path.join(output_json_dir, json_filename)

#                 with open(json_path, "w", encoding="utf-8") as f:
#                     if isinstance(final_json, str):
#                         f.write(final_json)
#                     else:
#                         json.dump(final_json, f, indent=2, ensure_ascii=False)

#                 results[roll_number] = {
#                     "json_path": json_path,
#                     "images_dir": output_images_dir,
#                     "pages_processed": len(sorted_images),
#                 }

#                 logger.info(f"Successfully processed roll {roll_number}")

#             except Exception as e:
#                 logger.error(f"Error processing roll {roll_number}: {str(e)}")
#                 results[roll_number] = {"error": str(e)}

#         if not results:
#             return {
#                 "success": False,
#                 "error": "No roll numbers could be processed successfully",
#             }

#         # Return results for the first successful roll number
#         # (you might want to modify this logic based on your needs)
#         for roll_number, result in results.items():
#             if "json_path" in result:
#                 return {
#                     "success": True,
#                     "roll_number": roll_number,
#                     "json_path": result["json_path"],
#                     "images_dir": result["images_dir"],
#                     "pages_processed": result["pages_processed"],
#                     "all_results": results,
#                 }

#         # If no successful results, return the first error
#         first_error = next(iter(results.values()))
#         return {
#             "success": False,
#             "error": first_error.get("error", "Unknown processing error"),
#             "all_results": results,
#         }

#     except Exception as e:
#         logger.error(f"OCR processing failed: {str(e)}")
#         return {"success": False, "error": f"OCR processing failed: {str(e)}"}

def process_answer_ocr(file_path, output_json_dir, output_images_dir, user_id):
    """
    Optimized OCR pipeline:
    1. Batch Page Scanning (1 Call)
    2. Smart Cropping (Reduces Tokens)
    3. Single Extraction Call
    """
    metrics_csv_path = os.path.join(output_json_dir, f"{user_id}_ocr_metrics.csv")

    try:
        logger.info(f"Starting Optimized OCR for: {file_path}")

        # 1. Extract
        all_images_data = extract_images_from_pdf(file_path)
        if not all_images_data:
            return {"success": False, "error": "No images found"}
        
        raw_images = [img for _, img in all_images_data]
        
        # 2. Batch Scan (Optimization 1)
        # This replaces the loop that called 'scan_page_details' 20 times
        logger.info("Step 2: Batch scanning all pages...")
        batch_results = scan_all_pages_batch(raw_images)
        
        # Map results to images
        # If batch fails, fallback to raw order
        page_map = []
        if batch_results and len(batch_results) == len(raw_images):
            for res in batch_results:
                # Ensure index is valid
                if 0 <= res.page_index < len(raw_images):
                    page_map.append({
                        "img": raw_images[res.page_index],
                        "page_num": res.page_number,
                        "diagram": res.has_diagram
                    })
            # Sort by detected page number
            page_map.sort(key=lambda x: x["page_num"])
        else:
            logger.warning("Batch scan mismatch/fail. Using default PDF order.")
            for i, img in enumerate(raw_images):
                page_map.append({"img": img, "page_num": i+1, "diagram": True}) # Assume True on fallback

        # 3. Smart Crop & Prepare (Optimization 2)
        sorted_images = []
        diagram_flags = []
        
        logger.info("Step 3: Smart cropping content...")
        for item in page_map:
            # Crop whitespace to save Vision Tokens
            cropped = smart_crop_content(item["img"])
            sorted_images.append(cropped)
            diagram_flags.append(item["diagram"])

        # 4. Convert to PDF & Extract
        pdf_bytes = images_to_pdf_bytes(sorted_images)
        
        logger.info("Step 4: Extracting JSON...")
        raw_json = gemini_json_from_pdf(
            pdf_bytes, output_images_dir, user_id
        )

        # 5. Diagrams (YOLO) - Pass the CROPPED images
        # Note: YOLO works fine on cropped images as long as diagrams aren't cut off
        logger.info("Step 5: Processing diagrams...")
        final_json = detect_and_crop_diagrams(
            sorted_images, 
            raw_json, 
            output_images_dir, 
            user_id, 
            diagram_flags
        )

        # 6. Save
        json_filename = f"{user_id}_answers.json"
        json_path = os.path.join(output_json_dir, json_filename)
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(final_json)

        return {
            "success": True,
            "json_path": json_path,
            "images_dir": output_images_dir,
            "pages_processed": len(sorted_images),
        }

    except Exception as e:
        logger.error(f"OCR failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
    
    finally:
        try:
            save_ocr_metrics_csv(metrics_csv_path)
            print_ocr_metrics_summary()
            # Save metrics to database (user_id is actually the answer_upload.id)
            save_ocr_metrics_to_db(user_id)
        except Exception as e:
            logger.warning(f"Failed to save OCR metrics: {e}")
