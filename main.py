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
from pypdf.generic import NameObject, BooleanObject


app = FastAPI(title="Combined Signature Form PDF Generator")

PDF_TEMPLATE = "COMBINED_SIGNATURE_FORM_-_Template.pdf"

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


@app.get("/fields")
def inspect_pdf_fields():
    reader = PdfReader(PDF_TEMPLATE)
    fields = reader.get_fields()

    if not fields:
        return {"fields": [], "message": "No fillable fields found."}

    return {"fields": list(fields.keys())}


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
    reader = PdfReader(PDF_TEMPLATE)
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    if "/AcroForm" in reader.trailer["/Root"]:
        writer._root_object.update({
            NameObject("/AcroForm"): reader.trailer["/Root"]["/AcroForm"]
        })

        writer._root_object["/AcroForm"].update({
            NameObject("/NeedAppearances"): BooleanObject(True)
        })

    field_values = {
        "employer_name": payload.employer_name,
        "address": payload.address,
        "policy_effective_date": payload.policy_effective_date,
        "policy_situs_state": payload.policy_situs_state,

        "worksite_term_life": checkbox_value(payload.worksite_term_life),
        "group_accident": checkbox_value(payload.group_accident),
        "group_critical_illness": checkbox_value(payload.group_critical_illness),
        "group_disability": checkbox_value(payload.group_disability),
        "lifetime_benefit_term": checkbox_value(payload.lifetime_benefit_term),

        "executed_day": payload.executed_day,
        "executed_month": payload.executed_month,
        "executed_year": payload.executed_year,

        "signature_officer_page1": payload.signature_officer_page1,
        "print_name_title_officer": payload.print_name_title_officer,
        "authorized_agent_name": payload.authorized_agent_name,

        "employer_organization_name": payload.employer_organization_name,
        "signature_officer_page2": payload.signature_officer_page2,
        "officer_name_page2": payload.officer_name_page2,
        "officer_title_page2": payload.officer_title_page2,
        "date_page2": payload.date_page2,
    }

    for page in writer.pages:
        writer.update_page_form_field_values(page, field_values)

    safe_name = clean_filename(payload.employer_name or "combined_signature_form")
    output_path = OUTPUT_DIR / f"Combined_Signature_Form_{safe_name}_{unique_id}.pdf"

    with open(output_path, "wb") as output_file:
        writer.write(output_file)

    return str(output_path)


def checkbox_value(value: str) -> str:
    if not value:
        return ""

    normalized = str(value).strip().lower()

    if normalized in ["yes", "true", "checked", "1", "on", "selected"]:
        return "Yes"

    return ""


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
