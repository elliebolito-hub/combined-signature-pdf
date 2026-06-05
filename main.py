import io
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


app = FastAPI(title="Combined Signature Form PDF Generator")

PDF_TEMPLATE = "Combined_Signature_Form_Template.pdf"

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "generated_files"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class PacketRequest(BaseModel):
    contact_id: Optional[str] = ""
    email: Optional[str] = ""

    employer_name: Optional[str] = ""
    address: Optional[str] = ""
    policy_effective_date: Optional[str] = ""
    policy_situs_state: Optional[str] = ""

    worksite_term_life: Optional[str] = ""
    group_accident: Optional[str] = ""
    group_critical_illness: Optional[str] = ""
    group_disability: Optional[str] = ""
    lifetime_benefit_term: Optional[str] = ""

    executed_day: Optional[str] = ""
    executed_month: Optional[str] = ""
    executed_year: Optional[str] = ""

    signature_officer_page1: Optional[str] = ""
    print_name_title_officer: Optional[str] = ""
    authorized_agent_name: Optional[str] = ""

    employer_organization_name: Optional[str] = ""
    signature_officer_page2: Optional[str] = ""
    officer_name_page2: Optional[str] = ""
    officer_title_page2: Optional[str] = ""
    date_page2: Optional[str] = ""


@app.get("/")
def home():
    return {
        "status": "Combined Signature Form PDF Generator is running",
        "template": PDF_TEMPLATE,
        "output_dir": str(OUTPUT_DIR),
    }


@app.get("/files")
def list_generated_files():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = []

    for file_path in OUTPUT_DIR.iterdir():
        if file_path.is_file():
            files.append({
                "filename": file_path.name,
                "size_bytes": file_path.stat().st_size,
                "download_url": f"/download/{quote(file_path.name)}",
            })

    return {
        "output_dir": str(OUTPUT_DIR),
        "file_count": len(files),
        "files": files,
    }


@app.get("/download/{filename}")
def download_file(filename: str):
    safe_name = Path(filename).name
    file_path = OUTPUT_DIR / safe_name

    if not file_path.exists():
        available_files = [
            item.name for item in OUTPUT_DIR.iterdir()
            if item.is_file()
        ] if OUTPUT_DIR.exists() else []

        raise HTTPException(
            status_code=404,
            detail={
                "message": "File not found. The app may have restarted, redeployed, or the file was removed.",
                "requested_file": safe_name,
                "output_dir": str(OUTPUT_DIR),
                "available_files": available_files,
            },
        )

    return FileResponse(
        path=str(file_path),
        filename=safe_name,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "Cache-Control": "no-store",
        },
    )


@app.post("/generate")
def generate_pdf(
    request: Request,
    payload: PacketRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    expected_api_key = os.getenv("API_KEY")

    if expected_api_key and x_api_key != expected_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    unique_id = make_unique_id()
    completed_pdf = fill_pdf(payload, unique_id)

    pdf_filename = os.path.basename(completed_pdf)

    public_base_url = os.getenv("PUBLIC_BASE_URL")

    if public_base_url:
        base_url = public_base_url.rstrip("/")
    else:
        base_url = str(request.base_url).rstrip("/")

    pdf_url = f"{base_url}/download/{quote(pdf_filename)}"

    return {
        "status": "success",
        "message": "Combined Signature Form PDF generated",
        "pdf_file": pdf_filename,
        "pdf_url": pdf_url,
        "pdf_exists": os.path.exists(completed_pdf),
        "output_dir": str(OUTPUT_DIR),
        "contact_id": payload.contact_id,
        "email": payload.email,
    }


def fill_pdf(payload: PacketRequest, unique_id: str) -> str:
    template_path = Path(PDF_TEMPLATE)

    if not template_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Template PDF not found: {PDF_TEMPLATE}",
        )

    reader = PdfReader(str(template_path))
    writer = PdfWriter()

    page_count = len(reader.pages)

    for page_index in range(page_count):
        page = reader.pages[page_index]
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)

        overlay_pdf = create_overlay_for_page(
            payload=payload,
            page_index=page_index,
            page_width=page_width,
            page_height=page_height,
        )

        overlay_reader = PdfReader(overlay_pdf)
        overlay_page = overlay_reader.pages[0]

        page.merge_page(overlay_page)
        writer.add_page(page)

    safe_name = clean_filename(payload.employer_name or "combined_signature_form")
    output_path = OUTPUT_DIR / f"Combined_Signature_Form_{safe_name}_{unique_id}.pdf"

    with open(output_path, "wb") as output_file:
        writer.write(output_file)

    return str(output_path)


def create_overlay_for_page(
    payload: PacketRequest,
    page_index: int,
    page_width: float,
    page_height: float,
) -> io.BytesIO:
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))

    c.setFillColorRGB(0, 0, 0)

    if page_index == 0:
        draw_page_1(c, payload)

    if page_index == 1:
        draw_page_2(c, payload)

    c.save()
    packet.seek(0)

    return packet


def draw_page_1(c: canvas.Canvas, payload: PacketRequest):
    # Top fields
    draw_text(c, payload.employer_name, x=125, y=661, size=9, max_width=390)
    draw_text(c, payload.address, x=83, y=646, size=9, max_width=440)
    draw_text(c, payload.policy_effective_date, x=137, y=631, size=9, max_width=385)
    draw_text(c, payload.policy_situs_state, x=125, y=616, size=9, max_width=395)

    # Checkboxes
    draw_check(c, payload.worksite_term_life, x=40, y=588)
    draw_check(c, payload.group_accident, x=40, y=561)
    draw_check(c, payload.group_critical_illness, x=40, y=543)
    draw_check(c, payload.group_disability, x=40, y=525)
    draw_check(c, payload.lifetime_benefit_term, x=40, y=506)

    # Executed date
    draw_text(c, payload.executed_day, x=96, y=230, size=9, max_width=65)
    draw_text(c, payload.executed_month, x=198, y=230, size=9, max_width=65)
    draw_text(c, payload.executed_year, x=285, y=230, size=9, max_width=60)

    # Signature and officer fields
    draw_text(c, payload.signature_officer_page1, x=38, y=194, size=9, max_width=245)
    draw_text(c, payload.print_name_title_officer, x=322, y=194, size=9, max_width=245)
    draw_text(c, payload.authorized_agent_name, x=322, y=147, size=9, max_width=245)


def draw_page_2(c: canvas.Canvas, payload: PacketRequest):
    employer_org = payload.employer_organization_name or payload.employer_name
    signature_2 = payload.signature_officer_page2 or payload.signature_officer_page1

    draw_text(c, employer_org, x=38, y=618, size=9, max_width=245)

    draw_text(c, signature_2, x=38, y=368, size=9, max_width=245)
    draw_text(c, payload.officer_name_page2, x=327, y=368, size=9, max_width=245)
    draw_text(c, payload.officer_title_page2, x=38, y=302, size=9, max_width=245)
    draw_text(c, payload.date_page2, x=38, y=234, size=9, max_width=245)


def draw_text(
    c: canvas.Canvas,
    value: Optional[str],
    x: float,
    y: float,
    size: int = 9,
    max_width: float = 250,
):
    text = str(value or "").strip()

    if not text:
        return

    c.setFont("Helvetica", size)

    while c.stringWidth(text, "Helvetica", size) > max_width and len(text) > 3:
        text = text[:-1]

    c.drawString(x, y, text)


def draw_check(c: canvas.Canvas, value: Optional[str], x: float, y: float):
    if not is_checked(value):
        return

    c.setFont("Helvetica-Bold", 12)

    # Draw a simple check mark centered in the checkbox.
    c.drawString(x - 4, y - 5, "✓")


def is_checked(value: Optional[str]) -> bool:
    if value is None:
        return False

    normalized = str(value).strip().lower()

    return normalized in [
        "yes",
        "true",
        "checked",
        "1",
        "on",
        "selected",
        "y",
    ]


def clean_filename(value: str) -> str:
    allowed = []

    for char in value:
        if char.isalnum() or char in ["-", "_"]:
            allowed.append(char)
        elif char == " ":
            allowed.append("_")

    cleaned = "".join(allowed).strip("_")

    if not cleaned:
        cleaned = "combined_signature_form"

    return cleaned[:80]


def make_unique_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    return f"{timestamp}_{short_id}"
