import os
import re # Added re for natural sort
from io import BytesIO
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from grade.models import QuestionGrade, PreviousYearQuestionPaper, GeneratedQuestionPaper

User = get_user_model()

class PDFReportGenerator:
    def __init__(self, grading_result):
        self.grading_result = grading_result
        self.answer_upload = grading_result.answer_upload
        self.question_paper = self._get_question_paper()
        self.user = self._get_user()
        self.buffer = BytesIO()
        self.styles = getSampleStyleSheet()
        self._create_custom_styles()

    def _get_user(self):
        try:
            return User.objects.get(pk=self.grading_result.user_id)
        except User.DoesNotExist:
            return None

    def _get_question_paper(self):
        """Helper to retrieve the correct question paper object based on type."""
        au = self.answer_upload
        # Check explicit type if available, or fall back to checking fields
        if au.previous_year_question_paper:
            return au.previous_year_question_paper
        if au.generated_question_paper:
            return au.generated_question_paper
        if au.sample_question_paper:
            return au.sample_question_paper
        if au.organization_test:
            return au.organization_test
        if au.questions:
            return au.questions
        return None

    def _create_custom_styles(self):
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            leading=28,
            textColor=colors.HexColor('#1a365d'),  # Dark Blue
            alignment=TA_RIGHT,
            spaceAfter=20
        ))
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor('#2c5282'),
            spaceBefore=15,
            spaceAfter=10,
            allowWidows=0
        ))
        self.styles.add(ParagraphStyle(
            name='QuestionText',
            parent=self.styles['Normal'],
            fontSize=11,
            leading=14,
            textColor=colors.black,
            spaceAfter=6
        ))
        self.styles.add(ParagraphStyle(
            name='AnswerText',
            parent=self.styles['Normal'],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor('#2d3748'),
            leftIndent=0
        ))
        self.styles.add(ParagraphStyle(
            name='FeedbackText',
            parent=self.styles['Normal'],
            fontSize=10,
            leading=12,
            textColor=colors.HexColor('#718096'),
            eval=False
        ))
        self.styles.add(ParagraphStyle(
            name='ScoreLabel',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#718096'),
        ))
        self.styles.add(ParagraphStyle(
            name='ScoreValue',
            parent=self.styles['Normal'],
            fontSize=14,
            leading=16,
            textColor=colors.HexColor('#2f855a'),  # Green
            fontName='Helvetica-Bold'
        ))

    def _draw_header(self, canvas, doc):
        canvas.saveState()
        
        # Logo
        # Using self-contained logo in backend static folder
        logo_path = os.path.join(settings.BASE_DIR, "grade", "static", "logo.png")
        if os.path.exists(logo_path):
            try:
                # Draw logo (width ~1.5 inch, aspect ratio preserved)
                # canvas.drawImage(image, x, y, width=None, height=None, mask=None, preserveAspectRatio=False, anchor='c')
                # Y position: slightly lower than text baseline to align
                canvas.drawImage(logo_path, inch, A4[1] - 1.1*inch, width=1.5*inch, height=0.5*inch, preserveAspectRatio=True, mask='auto')
            except Exception as e:
                print(f"Error drawing logo: {e}")
                canvas.setFont('Helvetica-Bold', 28)
                canvas.setFillColor(colors.HexColor('#4299e1'))
                canvas.drawString(inch, A4[1] - inch, "Lysa")
        else:
            canvas.setFont('Helvetica-Bold', 28)
            canvas.setFillColor(colors.HexColor('#4299e1'))
            canvas.drawString(inch, A4[1] - inch, "Lysa")
        
        # Line below header
        canvas.setStrokeColor(colors.HexColor('#e2e8f0'))
        canvas.setLineWidth(1)
        canvas.line(inch, A4[1] - 1.2*inch, A4[0] - inch, A4[1] - 1.2*inch)
        
        # Footer
        canvas.setFont('Helvetica', 9)
        canvas.setFillColor(colors.gray)
        page_num = canvas.getPageNumber()
        text = f"Page {page_num}"
        canvas.drawRightString(A4[0] - inch, 0.75*inch, text)
        
        canvas.restoreState()

    def generate(self):
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            rightMargin=inch,
            leftMargin=inch,
            topMargin=1.5*inch,
            bottomMargin=inch
        )

        elements = []

        # 1. Report Title
        elements.append(Paragraph("Grading Report", self.styles['ReportTitle']))

        # 2. Test Info & Student Info (Side by Side)
        self._add_info_section(elements)
        elements.append(Spacer(1, 20))

        # 3. Score Summary Box
        self._add_score_summary(elements)
        elements.append(Spacer(1, 30))

        # 4. Detailed Questions
        elements.append(Paragraph("Detailed Breakdown", self.styles['SectionHeader']))
        self._add_questions_section(elements)

        # Build PDF
        doc.build(elements, onFirstPage=self._draw_header, onLaterPages=self._draw_header)
        self.buffer.seek(0)
        return self.buffer

    def _add_info_section(self, elements):
        # Prepare data
        if self.user:
            full_name = f"{self.user.first_name} {self.user.last_name}".strip()
            student_name = full_name if full_name else self.user.username
        else:
            student_name = f"User #{self.grading_result.user_id}"

        student_id = self.user.username if self.user else "N/A"
        date_str = self.grading_result.graded_at.strftime("%B %d, %Y") if self.grading_result.graded_at else "N/A"
        
        # Safe attribute access
        test_title = getattr(self.question_paper, 'test_title', getattr(self.question_paper, 'title', "Untitled Test"))
        subject = getattr(self.question_paper, 'subject', "N/A")
        board = getattr(self.question_paper, 'board', "N/A")
        
        set_number = getattr(self.question_paper, 'set_number', "N/A")
        qp_code = getattr(self.question_paper, 'qp_code', "N/A")
        
        # Determine specific fields based on paper type
        extra_info_label = "Year"
        extra_info_value = "N/A"
        
        if isinstance(self.question_paper, PreviousYearQuestionPaper):
            extra_info_value = str(self.question_paper.year)
        elif isinstance(self.question_paper, GeneratedQuestionPaper):
            extra_info_label = "Generated"
            extra_info_value = "Yes" # Or parse creation date/options if available
            
        data = [
            [
                Paragraph(f"<b>Student:</b><br/>{student_name}", self.styles['Normal']),
                Paragraph(f"<b>Date:</b><br/>{date_str}", self.styles['Normal']),
            ],
            [
                Paragraph(f"<b>Test:</b><br/>{test_title}", self.styles['Normal']),
                Paragraph(f"<b>Subject:</b><br/>{subject} ({board})", self.styles['Normal'])
            ],
            [
                Paragraph(f"<b>Set:</b><br/>{set_number}", self.styles['Normal']),
                Paragraph(f"<b>QP Code:</b><br/>{qp_code}", self.styles['Normal'])
            ]
        ]
        
        # Styling the Info Table
        t = Table(data, colWidths=[3*inch, 3*inch])
        t.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('PADDING', (0,0), (-1,-1), 6),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ]))
        elements.append(t)

    def _add_score_summary(self, elements):
        total = self.grading_result.total_score
        max_score = self.grading_result.max_possible_score
        percentage = self.grading_result.percentage
        
        # Determine Performance
        if percentage >= 90: grade, color = "Excellent", "#2f855a"
        elif percentage >= 75: grade, color = "Good", "#2b6cb0"
        elif percentage >= 50: grade, color = "Average", "#d69e2e"
        else: grade, color = "Needs Improvement", "#c53030"
        
        summary_style = ParagraphStyle(
            'Summary', parent=self.styles['Normal'], fontSize=12, leading=16, alignment=TA_CENTER
        )
        
        data = [[
            Paragraph("Total Score", self.styles['ScoreLabel']),
            Paragraph("Percentage", self.styles['ScoreLabel']),
            Paragraph("Performance", self.styles['ScoreLabel'])
        ], [
            Paragraph(f"{total} / {max_score}", self.styles['ScoreValue']),
            Paragraph(f"{percentage:.1f}%", self.styles['ScoreValue']),
            Paragraph(f"<font color='{color}'><b>{grade}</b></font>", self.styles['Normal'])
        ]]
        
        t = Table(data, colWidths=[2*inch, 2*inch, 2*inch])
        t.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#4299e1')),
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#ebf8ff')),
            ('PADDING', (0,0), (-1,-1), 15),
            ('ROUNDED', (0,0), (-1,-1), 8), # Round corners if supported or ignored
        ]))
        elements.append(t)

    def _add_questions_section(self, elements):
        # Fetch question grades linked to this result
        # Note: Depending on your model structure, you might access properties differently.
        # Assuming GradingResult -> QuestionGrade via related_name='question_grades'
        
        # Use Python list sorting for natural sort (Q1, Q2, Q10 instead of Q1, Q10, Q2)
        question_grades = list(self.grading_result.question_grades.all())
        
        def natural_keys(text):
            # Split into [text, number, text, number...] chunks
            return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', str(text))]
            
        question_grades.sort(key=lambda x: natural_keys(x.question_number))
        
        if not question_grades:
            elements.append(Paragraph("No detailed grading data available.", self.styles['Normal']))
            return

        for qg in question_grades:
            self._add_single_question(elements, qg)
            elements.append(Spacer(1, 15))

    def _add_single_question(self, elements, qg):
        # Helper to format text lists/dicts
        def clean_text(val):
            if isinstance(val, dict):
                 # This simple clean_text is no longer enough for complex content
                 return val.get('text', val.get('answer', str(val)))
            return str(val) if val else "N/A"

        q_number_raw = str(qg.question_number)
        # Normalize: strip leading Qs and ensure single Q
        q_num = q_number_raw.lstrip('Qq') or q_number_raw # Handle empty if strictly 'Q'
        display_q_num = f"Q{q_num}"
        
        if hasattr(qg, 'question_text') and qg.question_text:
             display_text = qg.question_text
        else:
             display_text = f"Question {display_q_num}"
             
        q_text = f"<b>{display_q_num}:</b> {display_text}"
        
        score_str = f"{qg.obtained_marks}/{qg.allocated_marks}"
        
        # --- NEW: Process Student Answer Content ---
        # Instead of a single text paragraph, we generate a list of flowables
        student_content = self._render_student_content(qg.student_answer)
        
        # -------------------------------------------
        
        # Feedback formatting
        feedback_html = ""
        # Criteria
        criteria = qg.criteria_grades.all()
        if criteria.exists():
            feedback_html += "<b>Criteria Feedback:</b><br/>"
            for c in criteria:
                feedback_html += f"&bull; <i>{c.criterion_text}:</i> {c.feedback} ({c.obtained_marks}/{c.allocated_marks})<br/>"
        
        # Concept Analysis
        if hasattr(qg, 'concept_analysis') and qg.concept_analysis:
             feedback_html += "<br/><b>Concept Analysis:</b><br/>"
             # Check if it's a list (new format) or dict
             concepts = qg.concept_analysis
             if isinstance(concepts, list):
                 for c in concepts:
                     name = c.get('concept_name', 'Concept')
                     mastery = c.get('mastery_class', 'N/A')
                     acc = c.get('concept_accuracy_percentage', 0)
                     feedback_html += f"&bull; <b>{name}</b>: {mastery} ({acc}%)<br/>"
             
        # Confidence
        if hasattr(qg, 'confidence_percentage') and qg.confidence_percentage:
            conf_val = qg.confidence_percentage
            conf_lvl = getattr(qg, 'confidence_level', 'N/A')
            feedback_html += f"<br/><b>AI Confidence:</b> {conf_val}% ({conf_lvl})<br/>"
        
        # Main Table for Question
        # Row 1: Question Header (Marks on right)
        # Row 2: Student Answer
        # Row 3: Feedback
        
        # Styles
        style_q = self.styles['QuestionText']
        style_ans = self.styles['AnswerText']
        style_feed = self.styles['FeedbackText']
        
        # Construct Table Data
        # [ Question ... Marks ]
        # [ Answer Label ... ]
        # [ Answer Text ... ]
        # [ Feedback ... ]
        
        # Construct Table Data
        # [ Question ... Marks ]
        # [ Answer Label ... ]
        # [ Answer Content (Nested Table or Flowables) ... ]
        # [ Feedback ... ]
        
        data = [
            [Paragraph(q_text, style_q), Paragraph(f"<b>{score_str}</b>", self.styles['Normal'])],
            [Paragraph("<b>Student Answer:</b>", self.styles['Normal']), ''],
            [student_content, ''], # Pass the list of flowables here? No, Table needs flowables in cell
            [Paragraph("<b>Feedback:</b>", self.styles['Normal']), ''],
            [Paragraph(feedback_html, style_feed), '']
        ]
        # Note: student_content is a list of flowables. putting it in a list makes it a cell content.
        
        col_widths = [5 * inch, 1 * inch]
        
        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ('SPAN', (0,1), (1,1)), # Answer Label span
            ('SPAN', (0,2), (1,2)), # Answer Text span
            ('SPAN', (0,3), (1,3)), # Feedback Label span
            ('SPAN', (0,4), (1,4)), # Feedback Text span
            
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('ALIGN', (1,0), (1,0), 'RIGHT'), # Marks align right
            
            ('BACKGROUND', (0,0), (1,0), colors.HexColor('#f7fafc')), # Header bg
            ('LINEABOVE', (0,0), (1,0), 1, colors.HexColor('#cbd5e0')),
            ('LINEBELOW', (0,4), (1,4), 1, colors.HexColor('#cbd5e0')),
            
            ('PADDING', (0,0), (-1,-1), 8),
        ]))
        
        elements.append(KeepTogether(t))

    def _resolve_media_path(self, path_str):
        """Resolves metadata path to absolute file system path."""
        if not path_str:
            return None
        clean_path = str(path_str).replace("\\", "/")
        if clean_path.startswith("media/"):
            clean_path = clean_path.replace("media/", "", 1)
        full_path = os.path.join(settings.MEDIA_ROOT, clean_path)
        return full_path

    def _render_student_content(self, student_answer):
        """Generates a list of flowables for the student answer cell."""
        content = []
        if not student_answer:
            content.append(Paragraph("N/A", self.styles['AnswerText']))
            return content
            
        if not isinstance(student_answer, dict):
            # Fallback for simple string
            content.append(Paragraph(str(student_answer), self.styles['AnswerText']))
            return content

        # 1. Text
        text_val = student_answer.get('text') or student_answer.get('answer')
        if text_val:
            content.append(Paragraph(str(text_val), self.styles['AnswerText']))

        # 2. Diagrams
        diagrams = student_answer.get('diagram')
        if diagrams and isinstance(diagrams, dict):
            content.append(Spacer(1, 4))
            content.append(Paragraph("<b>Diagrams:</b>", self.styles['Normal']))
            for d_path in diagrams.values():
                full_path = self._resolve_media_path(d_path)
                if full_path and os.path.exists(full_path):
                    try:
                        # Resize image to fit comfortably (max width 4 inch)
                        img = Image(full_path, width=3*inch, height=2*inch, kind='proportional')
                        content.append(img)
                        content.append(Spacer(1, 4))
                    except Exception as e:
                        content.append(Paragraph(f"[Image Error: {e}]", self.styles['ScoreLabel']))

        # 3. Tables
        tables = student_answer.get('tables')
        if tables:
            content.append(Spacer(1, 4))
            content.append(Paragraph("<b>Tables:</b>", self.styles['Normal']))
            if isinstance(tables, list):
                for tbl in tables:
                    if isinstance(tbl, list) and len(tbl) > 0:
                        # tbl is list of rows
                        # Convert all cells to Paragraphs or strings
                        formatted_tbl = []
                        for row in tbl:
                            formatted_row = [Paragraph(str(cell), self.styles['AnswerText']) for cell in row]
                            formatted_tbl.append(formatted_row)
                        
                        t_obj = Table(formatted_tbl)
                        t_obj.setStyle(TableStyle([
                            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                            ('VALIGN', (0,0), (-1,-1), 'TOP'),
                            ('padding', (0,0), (-1,-1), 4),
                        ]))
                        content.append(t_obj)
                        content.append(Spacer(1, 4))
            elif isinstance(tables, str):
                 content.append(Paragraph(tables, self.styles['AnswerText']))

        # 4. Equations (Text representation)
        equations = student_answer.get('equations')
        if equations:
            content.append(Spacer(1, 4))
            content.append(Paragraph("<b>Equations:</b>", self.styles['Normal']))
            if isinstance(equations, list):
                for eq in equations:
                    # Rendering LaTeX is hard directly, showing as raw code or text
                    content.append(Paragraph(f"<i>{str(eq)}</i>", self.styles['AnswerText']))
            elif isinstance(equations, str):
                content.append(Paragraph(f"<i>{equations}</i>", self.styles['AnswerText']))
                
        if not content:
            content.append(Paragraph("N/A", self.styles['AnswerText']))
            
        return content
