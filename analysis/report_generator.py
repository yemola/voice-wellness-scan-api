from fpdf import FPDF
from datetime import datetime

class WellnessReport(FPDF):
    def header(self):
        # Header with Logo-like text
        self.set_font("helvetica", "B", 20)
        self.set_text_color(45, 120, 255) # Vocera Blue
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
    # Map common unicode characters to latin-1 equivalents
    replacements = {
        "\u2013": "-", # en dash
        "\u2014": "-", # em dash
        "\u2018": "'", # left single quote
        "\u2019": "'", # right single quote
        "\u201c": '"', # left double quote
        "\u201d": '"', # right double quote
        "\u2022": "-", # bullet point
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    
    # Fallback: encode to latin-1 and ignore anything else
    return text.encode("latin-1", "ignore").decode("latin-1")

def generate_pdf_report(data: dict) -> bytes:
    """
    Generates a PDF report from analysis data.
    data: {
        "scores": {"stress": int, "energy": int, "stability": int, "emotional_tone": str},
        "summary": str,
        "tips": list[str],
        "raw_features": dict,
        "user_id": str (optional)
    }
    """
    pdf = WellnessReport()
    pdf.add_page()
    
    scores = data.get("scores", {})
    summary = _clean_text(data.get("summary", "No summary available."))
    tips = [_clean_text(t) for t in data.get("tips", [])]
    features = data.get("raw_features", {})
    tone = _clean_text(scores.get("emotional_tone", "Balanced").capitalize())
    
    # --- PART 1: Executive Summary (Brief & Understandable) ---
    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, _clean_text("1. Executive Summary"), ln=True)
    pdf.ln(2)
    
    # Score Gauges (Visualized as colored boxes)
    pdf.set_font("helvetica", "B", 12)
    
    def add_score_row(label, value, color):
        pdf.set_fill_color(*color)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(40, 10, _clean_text(f" {label}"), fill=True)
        pdf.set_fill_color(240, 240, 240)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(20, 10, _clean_text(f"{value}%"), fill=True, align="C")
        pdf.ln(12)

    # Colors: Stress (Orange), Energy (Green), Stability (Blue)
    add_score_row("STRESS LOAD", scores.get("stress", 0), (255, 140, 0))
    add_score_row("VOCAL ENERGY", scores.get("energy", 0), (34, 139, 34))
    add_score_row("STABILITY", scores.get("stability", 0), (70, 130, 180))
    
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 10, _clean_text(f"Vocal Vibe: {tone}"), ln=True)
    
    pdf.set_font("helvetica", "", 11)
    pdf.multi_cell(0, 6, summary)
    pdf.ln(10)
    
    # Relaxation Suggestions
    pdf.set_fill_color(230, 242, 255) # Light blue bg
    pdf.rect(10, pdf.get_y(), 190, 45, "F")
    
    pdf.set_y(pdf.get_y() + 5)
    pdf.set_x(15)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 8, _clean_text("Daily Wellness & Calmness Tips"), ln=True)
    
    pdf.set_font("helvetica", "", 10)
    pdf.set_text_color(50, 50, 50)
    
    # Custom relaxation tips based on stress
    if scores.get("stress", 0) > 55:
        relax_tips = [
            "- Box Breathing: Inhale for 4s, hold for 4s, exhale for 4s, hold for 4s.",
            "- Progressive Muscle Relaxation: Tense and release your shoulders.",
            "- Hydration: Sip warm water or herbal tea to soothe vocal cords."
        ]
    else:
        relax_tips = [
            "- Maintain your current routine; your vocal signals are well-balanced.",
            "- Practice 5 minutes of mindful silence to sustain this stability.",
            "- Record a baseline when you feel 'neutral' for more accurate tracking."
        ]
        
    for tip in relax_tips:
        pdf.set_x(15)
        pdf.cell(0, 6, _clean_text(tip), ln=True)
    
    pdf.ln(20)
    
    # --- PART 2: Detailed Technical Analysis ---
    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, _clean_text("2. Detailed Technical Breakdown"), ln=True)
    pdf.ln(5)
    
    pdf.set_font("helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 5, _clean_text("These metrics are derived from micro-variations in your vocal signal. They provide a high-resolution look at the physiology behind your voice."))
    pdf.ln(5)
    
    # Technical Table
    pdf.set_font("helvetica", "B", 10)
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(60, 8, _clean_text(" Metric"), border=1, fill=True)
    pdf.cell(40, 8, _clean_text(" Value"), border=1, fill=True)
    pdf.cell(90, 8, _clean_text(" Meaning"), border=1, fill=True)
    pdf.ln()
    
    pdf.set_font("helvetica", "", 9)
    tech_data = [
        ("Jitter (Local)", f"{features.get('jitter', 0):.4f}", "Pitch irregularity. Often higher under acute stress."),
        ("Shimmer (Local)", f"{features.get('shimmer', 0):.4f}", "Amplitude variation. Linked to vocal intensity & breath control."),
        ("HNR", f"{features.get('hnr', 0):.2f} dB", "Harmonics-to-Noise Ratio. Clarity of the vocal signal."),
        ("Speech Rate", f"{features.get('speechRate', 0):.2f} syl/s", "Pacing of speech. Reflects arousal levels."),
        ("Pitch Stability", f"{scores.get('stability', 0)}%", "Consistency of fundamental frequency over time.")
    ]
    
    for metric, val, meaning in tech_data:
        pdf.cell(60, 8, _clean_text(f" {metric}"), border=1)
        pdf.cell(40, 8, _clean_text(f" {val}"), border=1, align="C")
        pdf.cell(90, 8, _clean_text(f" {meaning}"), border=1)
        pdf.ln()
        
    pdf.ln(10)
    pdf.set_font("helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.multi_cell(0, 4, _clean_text("Disclaimer: This report is for general wellness tracking only. It is not a medical diagnostic tool. If you have persistent health concerns, please consult a healthcare professional."))

    return pdf.output()
