from fpdf import FPDF
from datetime import datetime
import math
import logging

_log = logging.getLogger("report_generator")

class WellnessReport(FPDF):
    def header(self):
        self.set_font("helvetica", "B", 20)
        self.set_text_color(45, 120, 255)
        self.cell(0, 10, "VOCERA", ln=True, align="L")
        self.set_font("helvetica", "", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, "Personal Voice Wellness Report", ln=True, align="L")
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()} | Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C")

def _clean_text(text: str) -> str:
    """Ensures text is compatible with latin-1 (standard PDF fonts)."""
    if not text:
        return ""
    replacements = {
        "\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u2022": "-",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text.encode("latin-1", "ignore").decode("latin-1")

def _draw_radar_chart(pdf, x_center, y_center, radius, data_points):
    """
    Draws a custom radar chart (Acoustic Fingerprint) on the PDF.
    data_points: list of (label, value_0_to_100)
    """
    num_vars = len(data_points)
    angle_step = (2 * math.pi) / num_vars
    
    # 1. Draw background "web" (concentric polygons)
    pdf.set_draw_color(220, 220, 220)
    pdf.set_line_width(0.2)
    for r_factor in [0.25, 0.5, 0.75, 1.0]:
        r = radius * r_factor
        points = []
        for i in range(num_vars):
            angle = i * angle_step - (math.pi / 2)
            px = x_center + r * math.cos(angle)
            py = y_center + r * math.sin(angle)
            points.append((px, py))
        
        for i in range(num_vars):
            p1 = points[i]
            p2 = points[(i + 1) % num_vars]
            pdf.line(p1[0], p1[1], p2[0], p2[1])

    # 2. Draw axes and labels
    pdf.set_font("helvetica", "B", 7)
    pdf.set_text_color(100, 100, 100)
    for i, (label, _) in enumerate(data_points):
        angle = i * angle_step - (math.pi / 2)
        # Axis line
        ax = x_center + radius * math.cos(angle)
        ay = y_center + radius * math.sin(angle)
        pdf.line(x_center, y_center, ax, ay)
        
        # Label position (slightly outside the radius)
        lx = x_center + (radius + 8) * math.cos(angle) - 10
        ly = y_center + (radius + 5) * math.sin(angle) - 2
        pdf.text(lx, ly, _clean_text(label))

    # 3. Draw the data polygon (The Fingerprint)
    pdf.set_draw_color(45, 120, 255)
    pdf.set_line_width(0.8)
    data_coords = []
    for i, (_, val) in enumerate(data_points):
        # Constrain value to 0-100
        val = max(5, min(100, val or 0)) 
        angle = i * angle_step - (math.pi / 2)
        r = radius * (val / 100.0)
        px = x_center + r * math.cos(angle)
        py = y_center + r * math.sin(angle)
        data_coords.append((px, py))
    
    # Draw polygon lines
    for i in range(num_vars):
        p1 = data_coords[i]
        p2 = data_coords[(i + 1) % num_vars]
        pdf.line(p1[0], p1[1], p2[0], p2[1])
        # Draw small points at vertices
        pdf.ellipse(p1[0]-1, p1[1]-1, 2, 2, style="F")

def generate_pdf_report(data: dict) -> bytes:
    try:
        pdf = WellnessReport()
        pdf.add_page()
        
        scores = data.get("scores") or {}
        summary = _clean_text(data.get("summary") or "No summary available.")
        tips = [_clean_text(t) for t in data.get("tips", [])]
        features = data.get("raw_features") or {}
        tone = _clean_text(str(scores.get("emotional_tone", "Balanced")).capitalize())
        
        # --- PART 1: Executive Summary ---
        pdf.set_font("helvetica", "B", 16)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 10, _clean_text("1. Executive Summary"), ln=True)
        pdf.ln(2)
        
        # Draw the Fingerprint (Radar Chart) on the right side
        chart_x = 155
        chart_y = 55
        # Map features to chart points
        stability = scores.get("stability", 50)
        energy = scores.get("energy", 50)
        clarity = max(0, min(100, (features.get("hnr", 15) / 30) * 100)) # Scale HNR 0-30 to 0-100
        control = max(0, min(100, (1.0 - features.get("jitter", 0.01)*20) * 100)) # Inverse jitter
        tempo = max(0, min(100, (features.get("speechRate", 4) / 8) * 100)) # Scale rate
        
        fingerprint_data = [
            ("Stability", stability),
            ("Energy", energy),
            ("Clarity", clarity),
            ("Control", control),
            ("Tempo", tempo)
        ]
        _draw_radar_chart(pdf, chart_x, chart_y, 25, fingerprint_data)
        
        # Shift back to draw score rows on the left
        pdf.set_y(35) 
        def add_score_row(label, value, color):
            val = int(value) if value is not None else 0
            pdf.set_fill_color(*color)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(40, 10, _clean_text(f" {label}"), fill=True)
            pdf.set_fill_color(240, 240, 240)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(20, 10, f"{val}%", fill=True, align="C")
            pdf.ln(12)

        add_score_row("STRESS LOAD", scores.get("stress"), (255, 140, 0))
        add_score_row("VOCAL ENERGY", scores.get("energy"), (34, 139, 34))
        add_score_row("STABILITY", scores.get("stability"), (70, 130, 180))
        
        pdf.ln(10)
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(0, 10, _clean_text(f"Vocal Vibe: {tone}"), ln=True)
        
        pdf.set_font("helvetica", "", 11)
        pdf.multi_cell(120, 6, summary) # Narrowed to leave room for chart
        pdf.ln(10)
        
        # Suggestions Box
        pdf.set_fill_color(230, 242, 255)
        pdf.rect(10, pdf.get_y(), 190, 45, "F")
        pdf.set_y(pdf.get_y() + 5)
        pdf.set_x(15)
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 8, _clean_text("Daily Wellness & Calmness Tips"), ln=True)
        
        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(50, 50, 50)
        for tip in tips:
            pdf.set_x(15)
            pdf.cell(0, 6, f"- {tip}", ln=True)
        
        pdf.ln(20)
        
        # --- PART 2: Technical Breakdown ---
        pdf.set_font("helvetica", "B", 16)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 10, _clean_text("2. Detailed Technical Breakdown"), ln=True)
        pdf.ln(5)
        
        def get_f(key, d=0.0): return float(features.get(key) or d)

        tech_data = [
            ("Jitter (Local)", f"{get_f('jitter'):.4f}", "Pitch irregularity. Higher under acute stress."),
            ("Shimmer (Local)", f"{get_f('shimmer'):.4f}", "Amplitude variation. Linked to vocal intensity."),
            ("HNR", f"{get_f('hnr'):.2f} dB", "Harmonics-to-Noise Ratio. Clarity of the signal."),
            ("Speech Rate", f"{get_f('speechRate'):.2f} syl/s", "Pacing of speech. Reflects arousal levels."),
            ("Pitch Stability", f"{scores.get('stability') or 0}%", "Consistency of fundamental frequency.")
        ]
        
        pdf.set_font("helvetica", "B", 10)
        pdf.set_fill_color(220, 220, 220)
        pdf.cell(60, 8, _clean_text(" Metric"), border=1, fill=True)
        pdf.cell(40, 8, _clean_text(" Value"), border=1, fill=True)
        pdf.cell(90, 8, _clean_text(" Meaning"), border=1, fill=True)
        pdf.ln()
        
        pdf.set_font("helvetica", "", 9)
        for m, v, msg in tech_data:
            pdf.cell(60, 8, _clean_text(f" {m}"), border=1)
            pdf.cell(40, 8, _clean_text(f" {v}"), border=1, align="C")
            pdf.cell(90, 8, _clean_text(f" {msg}"), border=1)
            pdf.ln()
            
        pdf.ln(10)
        pdf.set_font("helvetica", "I", 8)
        pdf.set_text_color(150, 150, 150)
        disclaimer = "Disclaimer: This report is for general wellness tracking only. It is not a medical diagnostic tool. If you have persistent health concerns, please consult a healthcare professional."
        pdf.multi_cell(0, 4, _clean_text(disclaimer))

        return bytes(pdf.output())
    except Exception as e:
        _log.error(f"PDF Generation failed: {e}")
        raise e
