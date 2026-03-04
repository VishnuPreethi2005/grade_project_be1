"""
Task definitions for the grade app.

Defines background or utility tasks for grading, OCR, or related features.
"""
# tasks.py
from celery import shared_task
from django.conf import settings
import os
import logging
from .models import (
    AnswerUpload, 
    GradingResult, 
    Notification, 
    QuestionGrade, 
    CriteriaGrade, 
    AIMetrics
)
from authentication.models import User
from .ocr_processor import process_answer_ocr
from .grading import StudentGrader
from django.utils import timezone
import json
import csv
import glob
from pathlib import Path
from django.db.models import Sum
from django.core.files.storage import default_storage
import tempfile
import shutil


logger = logging.getLogger(__name__)

def determine_user_role(user: User) -> str:
    """Helper to determine the best role string for a user."""
    if user.active_role:
        return user.active_role
    # Fallback inference
    if user.is_student: return "student"
    if user.is_evaluator: return "evaluator"
    if user.is_qp_uploader: return "qp_uploader"
    if user.is_mentor: return "mentor"
    if user.is_admin: return "admin"
    return "student"  # Default fallback



@shared_task(bind=True)
def process_ocr_task(self, answer_upload_id: int) -> dict:
    """
    Asynchronous OCR processing task.

    Args:
        self: The task instance (provided by Celery when bind=True).
        answer_upload_id (int): The ID of the AnswerUpload object to process.

    Returns:
        dict: A dictionary with the result of the OCR processing, including success status, answer_upload_id, and message or error.
    """
    try:
        answer_upload = AnswerUpload.objects.get(id=answer_upload_id)

        # Create directories
        upload_id = str(answer_upload.id)
        output_base_dir = os.path.join(
            settings.MEDIA_ROOT, "output", upload_id
        )
        json_dir = os.path.join(output_base_dir, "json")
        images_dir = os.path.join(output_base_dir, "images")

        os.makedirs(json_dir, exist_ok=True)
        os.makedirs(images_dir, exist_ok=True)

        # Get the file - handle both local and blob storage
        file_path = None
        temp_file_path = None
        
        try:
            # Check if file exists locally (local storage)
            local_path = os.path.join(settings.MEDIA_ROOT, answer_upload.file.name)
            if os.path.exists(local_path):
                file_path = local_path
                logger.info(f"Using local file: {file_path}")
            else:
                # File is in blob storage, download temporarily
                logger.info(f"File not found locally, downloading from blob storage: {answer_upload.file.name}")
                temp_dir = tempfile.mkdtemp()
                temp_file_path = os.path.join(temp_dir, os.path.basename(answer_upload.file.name))
                
                # Download from blob storage
                with default_storage.open(answer_upload.file.name, 'rb') as source_file:
                    with open(temp_file_path, 'wb') as dest_file:
                        shutil.copyfileobj(source_file, dest_file)
                
                file_path = temp_file_path
                logger.info(f"Downloaded file from blob storage to: {file_path}")
        except Exception as e:
            logger.error(f"Error accessing file {answer_upload.file.name}: {e}")
            raise

        # Process OCR
        try:
            ocr_result = process_answer_ocr(
                file_path=file_path,
                output_json_dir=json_dir,
                output_images_dir=images_dir,
                user_id=answer_upload.user_id,
            )
        finally:
            # Clean up temporary file if downloaded from blob storage
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                    os.rmdir(os.path.dirname(temp_file_path))
                    logger.info(f"Cleaned up temporary file: {temp_file_path}")
                except Exception as cleanup_err:
                    logger.warning(f"Failed to clean up temporary file: {cleanup_err}")

        # Update the answer upload
        if ocr_result["success"]:
            answer_upload.ocr_processed = True
            answer_upload.ocr_json_path = ocr_result["json_path"]
            answer_upload.ocr_images_dir = ocr_result["images_dir"]
            # answer_upload.roll_number = ocr_result.get("roll_number")
            
            # --- NOTIFICATION (Success) ---
            try:
                user = User.objects.get(id=answer_upload.user_id)
                Notification.objects.create(
                    recipient=user,
                    sender=user, # System notification, self-sent or admin
                    sender_role="admin", # 'admin' or 'system'
                    recipient_role=determine_user_role(user),
                    message=f"OCR processing for your answer sheet (ID: {answer_upload.id}) completed successfully.",
                    is_read=False,
                    reference_id=answer_upload.id,
                    on_click_url=f"/upload_answer/{answer_upload.id}"
                )
            except Exception as notif_err:
                logger.error(f"Failed to create OCR success notification: {notif_err}")

        else:
            answer_upload.ocr_processed = False
            answer_upload.ocr_error = ocr_result.get(
                "error", "OCR processing failed"
            )
            
            # --- NOTIFICATION (Failure) ---
            try:
                user = User.objects.get(id=answer_upload.user_id)
                Notification.objects.create(
                    recipient=user,
                    sender=user,
                    sender_role="admin",
                    recipient_role=determine_user_role(user),
                    message=f"OCR processing failed for answer sheet (ID: {answer_upload.id}): {answer_upload.ocr_error}",
                    is_read=False,
                    reference_id=answer_upload.id,
                    on_click_url=f"/upload_answer/{answer_upload.id}"
                )
            except Exception as notif_err:
                logger.error(f"Failed to create OCR failure notification: {notif_err}")

        answer_upload.save()

        # If OCR success, sync metrics
        if answer_upload.ocr_processed and answer_upload.ocr_json_path:
             ocr_folder = os.path.dirname(answer_upload.ocr_json_path)
             try:
                 sync_csv_metrics_to_db(answer_upload, ocr_folder, "OCR")
             except Exception as ocr_met_err:
                  logger.error(f"Error syncing OCR metrics: {ocr_met_err}")


        return {
            "success": ocr_result["success"],
            "answer_upload_id": answer_upload_id,
            "message": "OCR processing completed",
        }

    except Exception as e:
        logger.error(
            f"OCR task failed for upload {answer_upload_id}: {str(e)}"
        )
        # Update the record to indicate failure
        try:
            answer_upload = AnswerUpload.objects.get(id=answer_upload_id)
            answer_upload.ocr_processed = False
            answer_upload.ocr_error = str(e)
            answer_upload.save()
            
            # --- NOTIFICATION (Exception) ---
            user = User.objects.get(id=answer_upload.user_id)
            Notification.objects.create(
                recipient=user,
                sender=user,
                sender_role="admin",
                recipient_role=determine_user_role(user),
                message=f"OCR processing encountered an error for answer sheet (ID: {answer_upload.id}).",
                is_read=False,
                reference_id=answer_upload.id,
                on_click_url=f"/upload_answer/{answer_upload.id}"
            )
        except BaseException:
            pass

        return {
            "success": False,
            "answer_upload_id": answer_upload_id,
            "error": str(e),
        }


@shared_task(bind=True)
def grade_answer_task(self, answer_id: int) -> dict:
    """
    Asynchronous grading task.
    """
    logger.info(f"Starting background grading for answer {answer_id}")
    answer_key_temp_path = None  # Initialize for cleanup
    try:
        # Get the answer upload
        answer_upload = AnswerUpload.objects.get(id=answer_id)
        
        # Determine Answer Key Path (PDF or JSON)
        answer_key_path = None
        
        # 1. Check if it's a Previous Year paper with a specific answer key
        if answer_upload.question_paper_type == "previous_year" and answer_upload.previous_year_question_paper:
            qp = answer_upload.previous_year_question_paper
            if qp.answer_key:
                try:
                    # Try to access file - handle both local and blob storage
                    local_key_path = None
                    try:
                        # Try .path attribute (works for local storage)
                        local_key_path = qp.answer_key.path
                        if os.path.exists(local_key_path):
                            answer_key_path = local_key_path
                            logger.info(f"Using specific answer key for Previous Year Paper (local): {answer_key_path}")
                    except (ValueError, NotImplementedError):
                        # .path doesn't work for blob storage, download it
                        logger.info(f"Answer key in blob storage, downloading: {qp.answer_key.name}")
                        temp_dir = tempfile.mkdtemp()
                        answer_key_temp_path = os.path.join(temp_dir, os.path.basename(qp.answer_key.name))
                        
                        with default_storage.open(qp.answer_key.name, 'rb') as source_file:
                            with open(answer_key_temp_path, 'wb') as dest_file:
                                shutil.copyfileobj(source_file, dest_file)
                        
                        answer_key_path = answer_key_temp_path
                        logger.info(f"Downloaded answer key from blob storage to: {answer_key_path}")
                except Exception as e:
                    logger.warning(f"Could not access specific answer key: {e}")

        # 2. Fallback to default answer key if no specific key found
        if not answer_key_path:
            answer_key_path = os.path.join(
                settings.BASE_DIR, "grade", "answerkey.pdf"
            )
            logger.info(f"Using default answer key: {answer_key_path}")

        # Validate answer key file exists
        if not os.path.exists(answer_key_path):
             raise FileNotFoundError("Answer key file not found")

        # Create grading result record
        grading_result = GradingResult.objects.create(
            answer_upload=answer_upload,
            user_id=answer_upload.user_id,
            grading_processed=False,
        )

        try:
            # Setup grading directories
            output_folder = os.path.dirname(answer_upload.ocr_json_path)  # Directory containing JSON
            
            # This is the main folder for this specific grading result
            results_folder = os.path.join(
                settings.MEDIA_ROOT, "grading_results", str(grading_result.id)
            )
            
            # Create a dedicated, permanent folder for the answer key diagrams
            answer_key_diagram_folder = os.path.join(results_folder, "answer_key_imgs")

            os.makedirs(results_folder, exist_ok=True)
            os.makedirs(answer_key_diagram_folder, exist_ok=True)

            logger.info(f"Results folder: {results_folder}")

            # Initialize Grader
            grader = StudentGrader(answer_key_diagram_folder=answer_key_diagram_folder, answer_upload=answer_upload)
            
            # Prepare external assets if available
            external_assets = None
            if answer_upload.question_paper_type == "previous_year" and answer_upload.previous_year_question_paper:
                external_assets = answer_upload.previous_year_question_paper.assets

            grading_summary = grader.grade_all_students(
                output_folder=output_folder,
                results_folder=results_folder,
                answer_key_path=answer_key_path, # Passed the detected path (PDF or JSON)
                external_assets=external_assets,
            )

            # Find the result file for this specific answer
            result_file_pattern = f"*_result.json"
            result_files = list(Path(results_folder).glob(result_file_pattern))

            if result_files:
                # Take the first result file
                result_file_path = str(result_files[0])

                # Load the grading result JSON
                with open(result_file_path, "r", encoding="utf-8") as f:
                    result_data = json.load(f)

                # 1. Update GradingResult Summary in DB
                grading_result.total_score = result_data.get("total_score", 0)
                grading_result.max_possible_score = result_data.get("max_possible_score", 0)
                grading_result.percentage = (
                    (grading_result.total_score / grading_result.max_possible_score * 100)
                    if grading_result.max_possible_score > 0
                    else 0
                )
                grading_result.result_json_path = result_file_path
                grading_result.grading_processed = True
                grading_result.graded_at = timezone.now()
                grading_result.questions_count = len(result_data.get("results", []))
                grading_result.diagrams_count = result_data.get("grading_metadata", {}).get("student_diagrams_count", 0)
                grading_result.save()

                # --- NEW DB SYNC LOGIC ---
                
                # 2. Save Detailed Question & Criteria Data to DB
                try:
                    save_detailed_grading_to_db(grading_result, result_data)
                    logger.info(f"Detailed grading results saved to DB for {grading_result.id}")
                except Exception as db_err:
                    logger.error(f"Error saving detailed results to DB: {db_err}")

                # 3. Sync Grading Metrics (found in results_folder)
                try:
                    sync_csv_metrics_to_db(answer_upload, results_folder, "GRADING")
                except Exception as met_err:
                    logger.error(f"Error syncing grading metrics: {met_err}")

                # 4. Sync OCR Metrics (found in OCR output folder)
                if answer_upload.ocr_json_path:
                    ocr_folder = os.path.dirname(answer_upload.ocr_json_path)
                    try:
                        sync_csv_metrics_to_db(answer_upload, ocr_folder, "OCR")
                    except Exception as ocr_met_err:
                         logger.error(f"Error syncing OCR metrics: {ocr_met_err}")

                # 5. Print accurate combined summary AFTER all syncs complete
                try:
                    print_combined_metrics_summary(answer_upload)
                except Exception as sum_err:
                    logger.error(f"Error printing combined summary: {sum_err}")

                # --- END NEW DB SYNC LOGIC ---
                
                # --- NOTIFICATION (Success) ---
                try:
                    user = User.objects.get(id=answer_upload.user_id)
                    Notification.objects.create(
                        recipient=user,
                        sender=user,
                        sender_role="admin",
                        recipient_role=determine_user_role(user),
                        message=f"Grading completed for {answer_upload.file.name}. Score: {grading_result.total_score}/{grading_result.max_possible_score}",
                        is_read=False,
                        reference_id=answer_upload.id,
                        on_click_url=f"/upload_answer/{answer_upload.id}"
                    )
                except Exception as notif_err:
                    logger.error(f"Failed to create Grading success notification: {notif_err}")

                logger.info(f"Grading completed for answer {answer_id}")
                return {"success": True, "answer_id": answer_id, "score": grading_result.total_score}

            else:
                grading_result.grading_error = "No grading result file generated"
                grading_result.save()
                raise Exception("No grading result file generated")

        except Exception as grading_error:
            grading_result.grading_error = str(grading_error)
            grading_result.save()
            raise grading_error

    except Exception as e:
        logger.error(f"Grading task failed for answer {answer_id}: {str(e)}", exc_info=True)
         # --- NOTIFICATION (Failure) ---
        try:
             # Try to get user from answer_upload, might be undefined if get(id=) failed
             if 'answer_upload' in locals():
                user = User.objects.get(id=answer_upload.user_id)
                Notification.objects.create(
                    recipient=user,
                    sender=user,
                    sender_role="admin",
                    recipient_role=determine_user_role(user),
                    message=f"Grading failed for answer {answer_id}. Please try again.",
                    is_read=False,
                    reference_id=answer_upload.id,
                    on_click_url=f"/upload_answer/{answer_upload.id}"
                )
        except Exception:
            pass
        return {"success": False, "answer_id": answer_id, "error": str(e)}
    finally:
        # Clean up temporary answer key file if downloaded from blob storage
        if answer_key_temp_path and os.path.exists(answer_key_temp_path):
            try:
                os.remove(answer_key_temp_path)
                os.rmdir(os.path.dirname(answer_key_temp_path))
                logger.info(f"Cleaned up temporary answer key file: {answer_key_temp_path}")
            except Exception as cleanup_err:
                logger.warning(f"Failed to clean up temporary answer key file: {cleanup_err}")


# --- HELPER FUNCTIONS ---

def save_detailed_grading_to_db(grading_result, json_data):
    """
    Parses the result JSON and saves detailed Question and Criteria models 
    to the database for persistence.
    """
    # Clear existing details if re-grading to prevent duplicates
    QuestionGrade.objects.filter(grading_result=grading_result).delete()

    question_objs = []
    criteria_batch = []

    for q_data in json_data.get("results", []):
        # 1. Create QuestionGrade object
        q_grade = QuestionGrade.objects.create(
            grading_result=grading_result,
            question_number=q_data.get("question_number"),
            question_type=q_data.get("question_type"),
            allocated_marks=q_data.get("allocated_marks", 0),
            obtained_marks=q_data.get("obtained_marks", 0),
            student_answer=q_data.get("student_answer"),
            expected_answer=q_data.get("expected_answer"),
            summary=q_data.get("summary"),
            mistakes_identified=q_data.get("mistakes_identified", []),
            final_feedback=q_data.get("final_feedback"),
            general_feedback=q_data.get("general_feedback"),
            diagram_comparison=q_data.get("diagram_comparison"),
            
            # --- NEW: Concept Analysis & Confidence ---
            concept_analysis=q_data.get("concept_analysis"),
            confidence_percentage=q_data.get("confidence_percentage"),
            confidence_level=q_data.get("confidence_level")
        )

        # 2. Prepare CriteriaGrade objects (if breakdown exists)
        if "criteria_breakdown" in q_data and q_data["criteria_breakdown"]:
            for crit in q_data["criteria_breakdown"]:
                criteria_batch.append(CriteriaGrade(
                    question_grade=q_grade,
                    criterion_text=crit.get("criterion"),
                    allocated_marks=crit.get("allocated_marks", 0),
                    obtained_marks=crit.get("obtained_marks", 0),
                    feedback=crit.get("feedback"),
                    mistakes_found=crit.get("mistakes_found", [])
                ))
    
    # Bulk create criteria for performance
    if criteria_batch:
        CriteriaGrade.objects.bulk_create(criteria_batch)


def sync_csv_metrics_to_db(answer_upload, folder_path, process_type):
    """
    Finds the latest CSV, processes the data (Splitting OCR costs per question),
    and syncs to the DB. Robust against missing files.
    """
    # 1. Define pattern (wildcard * handles filename variations)
    prefix = "grading_metrics" if process_type == "GRADING" else "ocr_metrics"
    pattern = os.path.join(folder_path, f"*{prefix}*.csv")
    
    # 2. Find file
    files = glob.glob(pattern)
    if not files:
        logger.warning(f"⚠️ No {process_type} metrics CSV found matching: {pattern}")
        return

    # Use the most recent file
    latest_file = max(files, key=os.path.getctime)
    logger.info(f"Processing metrics file: {latest_file}")
    
    try:
        metrics_objs = []
        rows = []
        with open(latest_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            logger.warning(f"Metrics CSV {latest_file} is empty.")
            return

        # --- HELPER FUNCTIONS ---
        def safe_int(val):
            try: return int(float(val))
            except: return 0
        def safe_float(val):
            try: return float(val)
            except: return 0.0

        # Clear old data before inserting new
        AIMetrics.objects.filter(answer_upload=answer_upload, process_type=process_type).delete()

        # --- SPLITTING LOGIC ---
        if process_type == "OCR":
            # 1. Sum up the TOTAL cost of the entire OCR process
            total_input = sum(safe_int(r.get("input_tokens")) for r in rows)
            total_output = sum(safe_int(r.get("output_tokens")) for r in rows)
            total_cost = sum(safe_float(r.get("total_cost_usd")) for r in rows)
            # Use 'total_tokens' column if available, else calc sum
            total_tokens = sum(safe_int(r.get("total_tokens")) for r in rows)
            if total_tokens == 0: total_tokens = total_input + total_output

            # 2. Find out how many questions exist for this answer
            try:
                # Access the questions created in the grading step
                q_count = QuestionGrade.objects.filter(grading_result__answer_upload=answer_upload).count()
            except Exception as e:
                logger.warning(f"Could not count questions: {e}")
                q_count = 0

            if q_count > 0:
                # 3. Calculate Share per Question
                share_input = total_input // q_count
                share_output = total_output // q_count
                share_tokens = total_tokens // q_count
                share_cost = total_cost / q_count

                # 4. Create a DB record for EACH question
                questions = QuestionGrade.objects.filter(grading_result__answer_upload=answer_upload)
                for q in questions:
                    metrics_objs.append(AIMetrics(
                        answer_upload=answer_upload,
                        process_type="OCR",
                        identifier=str(q.question_number), 
                        input_tokens=share_input,
                        output_tokens=share_output,
                        total_tokens=share_tokens,
                        total_cost_usd=share_cost,
                        timestamp=timezone.now()
                    ))
                logger.info(f"Split Total OCR Cost (${total_cost:.4f}) among {q_count} questions.")
            
            else:
                # Fallback: If no questions found, save as "System Total"
                metrics_objs.append(AIMetrics(
                    answer_upload=answer_upload,
                    process_type="OCR",
                    identifier="Document Total",
                    input_tokens=total_input,
                    output_tokens=total_output,
                    total_tokens=total_tokens,
                    total_cost_usd=total_cost,
                    timestamp=timezone.now()
                ))

        else:
            # GRADING LOGIC (Already per-question, save as is)
            for row in rows:
                metrics_objs.append(AIMetrics(
                    answer_upload=answer_upload,
                    process_type="GRADING",
                    identifier=row.get("question", "Unknown"),
                    input_tokens=safe_int(row.get("input_tokens")),
                    output_tokens=safe_int(row.get("output_tokens")),
                    total_tokens=safe_int(row.get("total_tokens")),
                    total_cost_usd=safe_float(row.get("total_cost_usd")),
                    timestamp=timezone.now()  # Or parse from CSV if needed
                ))

        if metrics_objs:
            AIMetrics.objects.bulk_create(metrics_objs)
            logger.info(f"Successfully synced {len(metrics_objs)} {process_type} metrics to DB.")

    except Exception as e:
        logger.error(f"Error processing metrics CSV {latest_file}: {e}")

def print_combined_metrics_summary(answer_upload):
    """
    Print combined OCR + Grading metrics summary after DB sync.
    This ensures accurate totals since both are now in the database.
    """
    
    def get_metrics(process_type):
        metrics = AIMetrics.objects.filter(
            answer_upload=answer_upload, 
            process_type=process_type
        ).aggregate(
            total_input=Sum('input_tokens'),
            total_output=Sum('output_tokens'),
            total_tokens=Sum('total_tokens'),
            total_cost=Sum('total_cost_usd')
        )
        return {
            'input_tokens': metrics['total_input'] or 0,
            'output_tokens': metrics['total_output'] or 0,
            'total_tokens': metrics['total_tokens'] or 0,
            'total_cost': float(metrics['total_cost'] or 0),
            'call_count': AIMetrics.objects.filter(
                answer_upload=answer_upload, 
                process_type=process_type
            ).count()
        }
    
    ocr = get_metrics('OCR')
    grading = get_metrics('GRADING')
    
    combined_input = ocr['input_tokens'] + grading['input_tokens']
    combined_output = ocr['output_tokens'] + grading['output_tokens']
    combined_tokens = ocr['total_tokens'] + grading['total_tokens']
    combined_cost = ocr['total_cost'] + grading['total_cost']
    
    logger.info("==== 💰 COMBINED METRICS SUMMARY (OCR + GRADING) ====")
    logger.info(f"📝 OCR:      Input: {ocr['input_tokens']:,} | Output: {ocr['output_tokens']:,} | Total: {ocr['total_tokens']:,} | Cost: ${ocr['total_cost']:.6f} | Calls: {ocr['call_count']}")
    logger.info(f"📊 Grading:  Input: {grading['input_tokens']:,} | Output: {grading['output_tokens']:,} | Total: {grading['total_tokens']:,} | Cost: ${grading['total_cost']:.6f} | Calls: {grading['call_count']}")
    logger.info(f"💰 COMBINED: Input: {combined_input:,} | Output: {combined_output:,} | Total: {combined_tokens:,} | Cost: ${combined_cost:.6f}")
    logger.info("=====================================================")
