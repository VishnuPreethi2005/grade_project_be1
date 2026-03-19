import os
import re
from django.core.management.base import BaseCommand
from django.core.files import File
from grade.models import PreviousYearQuestionPaper
from django.utils import timezone
import wordninja
 
# Adjusted: Parse filenames by splitting on underscores, not regex
 
BOARD_DISPLAY_MAP = {
    "cbse": "CBSE",
    "tn": "TN board",
}
 
class Command(BaseCommand):
    help = 'Bulk import previous year question papers from a directory'
 
    def add_arguments(self, parser):
        parser.add_argument('directory', type=str, help='Directory containing the question paper files')
 
    def handle(self, *args, **options):
        directory = options['directory']
        count = 0
 
        for filename in os.listdir(directory):
            if not (filename.endswith('.pdf') or filename.endswith('.docx')):
                self.stdout.write(self.style.WARNING(f"Skipping file (not a PDF/DOCX): {filename}"))
                continue
 
            name_part = filename.rsplit('.', 1)[0]
            parts = name_part.split('_')
            if len(parts) != 6:
                self.stdout.write(self.style.WARNING(f"Skipping file (pattern not matched): {filename}"))
                continue
 
            board_raw, _class, subject, test_title, year, total_marks = [p.strip() for p in parts]
            total_marks = re.sub(r'\D', '', total_marks)
            board_display = BOARD_DISPLAY_MAP.get(board_raw.lower(), board_raw.upper())
            subject_words = wordninja.split(subject.lower())
            subject_display = ' '.join(word.capitalize() for word in subject_words)
            file_path = os.path.join(directory, filename)
 
            # Check if already imported
            if PreviousYearQuestionPaper.objects.filter(
                test_title=test_title,
                year=int(year),
                subject=subject_display,
                board=board_display,
                total_marks=int(total_marks)
            ).exists():
                self.stdout.write(self.style.NOTICE(f"Already exists: {filename}"))
                continue
 
            with open(file_path, 'rb') as f:
                paper = PreviousYearQuestionPaper(
                    test_title=test_title,
                    year=int(year),
                    subject=subject_display,
                    board=board_display,
                    total_marks=int(total_marks),
                    total_questions=0,  # Set if you can parse from filename or elsewhere
                    questions=[],  # You can parse questions if you have a way, else leave empty
                )
                paper.file.save(filename, File(f), save=True)
                count += 1
                self.stdout.write(self.style.SUCCESS(f"Imported: {filename}"))
 
        self.stdout.write(self.style.SUCCESS(f"Imported {count} files."))